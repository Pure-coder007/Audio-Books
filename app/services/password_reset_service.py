"""Forgotten passwords for author accounts and staff.

A reset link is single-use, lasts RESET_TTL, and only its SHA-256 hash is stored. Requesting a link
always shows the same message, and the lookup and email happen after the response is sent, so the
page never reveals whether an address has an account. Using a link signs the account out everywhere.
"""
import hashlib
import secrets
from datetime import timedelta
from types import SimpleNamespace
from flask import current_app, render_template, has_request_context
from sqlalchemy.exc import SQLAlchemyError
from ..extensions import db
from ..models import AuthorAccount, AdminUser, AuditLog, EmailDelivery, PasswordReset, now, uid

RESET_TTL = timedelta(minutes=30)
RESEND_GAP = timedelta(seconds=60)
KINDS = {
    'author': dict(model=AuthorAccount, path='/authors/reset/', min_length=10, audience='author'),
    'staff': dict(model=AdminUser, path='/admin/reset/', min_length=12, audience='staff'),
}


def digest(token):
    return hashlib.sha256((token or '').encode()).hexdigest()


def find_account(kind, email):
    model = KINDS[kind]['model']
    if kind == 'staff':
        return db.session.scalar(db.select(AdminUser).where(db.func.lower(AdminUser.email) == email, AdminUser.active.is_(True)))
    return db.session.scalar(db.select(model).where(model.email == email))


def account_name(kind, account):
    if kind == 'author':
        return account.first_name
    return None


def issue(kind, account):
    """Create a fresh link for an account, retiring any earlier unused ones. Returns the URL, or None if one was just sent."""
    recent = db.session.scalar(db.select(PasswordReset.id).where(PasswordReset.account_type == kind, PasswordReset.account_id == account.id,
        PasswordReset.created_at > now() - RESEND_GAP))
    if recent:
        return None
    db.session.execute(db.update(PasswordReset).where(PasswordReset.account_type == kind, PasswordReset.account_id == account.id,
        PasswordReset.used_at.is_(None)).values(used_at=now()))
    token = secrets.token_urlsafe(32)
    db.session.add(PasswordReset(token_hash=digest(token), account_type=kind, account_id=account.id, expires_at=now() + RESET_TTL))
    return current_app.config['BASE_URL'] + KINDS[kind]['path'] + token


def valid_reset(kind, token):
    reset = db.session.scalar(db.select(PasswordReset).where(PasswordReset.token_hash == digest(token), PasswordReset.account_type == kind))
    if not reset or reset.used_at or reset.expires_at <= now():
        return None, None
    account = db.session.get(KINDS[kind]['model'], reset.account_id)
    if not account or (kind == 'staff' and not account.active):
        return None, None
    return reset, account


def complete(kind, token, password):
    """Set the new password if the link is still good. Returns the account, or None."""
    from werkzeug.security import generate_password_hash
    reset, account = valid_reset(kind, token)
    if not reset:
        return None
    claimed = db.session.execute(db.update(PasswordReset).where(PasswordReset.id == reset.id, PasswordReset.used_at.is_(None),
        PasswordReset.expires_at > now()).values(used_at=now()))
    if claimed.rowcount != 1:
        db.session.rollback()
        return None
    account.password_hash = generate_password_hash(password)
    account.session_version = uid()
    db.session.execute(db.update(PasswordReset).where(PasswordReset.account_type == kind, PasswordReset.account_id == account.id,
        PasswordReset.used_at.is_(None)).values(used_at=now()))
    if kind == 'staff':
        db.session.add(AuditLog(admin_id=account.id, action='staff.password_reset', detail='Password reset with an emailed link; sessions invalidated'))
    db.session.commit()
    return account


def render_email(kind, mode, email, name=None, link=None):
    """Subject, plain text and HTML for a reset link (mode 'reset') or a changed-password notice (mode 'changed')."""
    if not has_request_context():
        with current_app.test_request_context(base_url=current_app.config['BASE_URL']):
            return render_email(kind, mode, email, name, link)
    base = current_app.config['BASE_URL']
    staff = kind == 'staff'
    minutes = int(RESET_TTL.total_seconds() // 60)
    when = now().strftime('%-d %B %Y at %H:%M') + ' UTC'
    if mode == 'reset':
        subject = 'Reset your Shelf studio password' if staff else 'Reset your MyAudioShelf password'
    else:
        subject = 'Your Shelf studio password was changed' if staff else 'Your MyAudioShelf password was changed'
    login_url = base + ('/admin/login' if staff else '/authors/login')
    forgot_url = base + ('/admin/forgot' if staff else '/authors/forgot')
    html = render_template('emails/password_reset.html', subject=subject, mode=mode, staff=staff, name=name, email=email, link=link,
        minutes=minutes, when=when, base_url=base, logo_url=base + '/static/images/brand/email-logo.png', login_url=login_url,
        forgot_url=forgot_url, contact_url=base + '/contact')
    greeting = f'Hi {name},' if name else 'Hello,'
    if mode == 'reset':
        text = [greeting, '', f'We received a request to reset the password for {email}' + (' on Shelf studio.' if staff else ' on MyAudioShelf.'), '',
                'Choose a new password: ' + link, '', f'This link works once and expires in {minutes} minutes.',
                f'Requested {when}.', '', 'Didn’t ask for this? Ignore this email and your password stays the same.']
    else:
        text = [greeting, '', f'The password for {email} was changed on {when}. You’ve been signed out on every other device.', '',
                'Log in: ' + login_url, '', 'Wasn’t you? Reset your password now: ' + forgot_url, 'and contact us: ' + base + '/contact']
    text += ['', 'MyAudioShelf · Stories worth listening to.']
    return subject, '\n'.join(text), html


def send(kind, mode, account, link=None):
    """Send now through Resend or SMTP. Without email set up (local development), keep it in the development outbox."""
    from .email_service import configured, send_email, DeliveryError
    subject, body, html = render_email(kind, mode, account.email, account_name(kind, account), link)
    record = EmailDelivery(recipient=account.email, subject=subject, body=body, html_body=html, delivery_key=uid())
    if not configured():
        if current_app.config['PRODUCTION']:
            current_app.logger.warning('Password email not sent: email delivery is not configured.')
            record.status, record.body, record.html_body = 'failed', '[Email delivery is not configured; link removed]', None
        else:
            record.status = 'development'
        db.session.add(record)
        return False
    try:
        record.provider_message_id = send_email(SimpleNamespace(recipient=account.email, subject=subject, body=body, html_body=html,
            delivery_key=record.delivery_key))
        record.status, record.sent_at = 'sent', now()
    except DeliveryError as error:
        record.status, record.last_error = 'failed', str(error)[:100]
        current_app.logger.warning('Password email could not be delivered.')
    record.attempts = 1
    # Never keep a usable link in the database.
    record.body, record.html_body = '[Password email submitted; link removed]', None
    db.session.add(record)
    return record.status == 'sent'


def request_reset(kind, email):
    """Look up the address and, if it has an account, email a link. Safe to run after the response."""
    try:
        account = find_account(kind, email)
        if not account:
            return
        link = issue(kind, account)
        if not link:
            return
        db.session.commit()
        send(kind, 'reset', account, link)
        if kind == 'staff':
            db.session.add(AuditLog(admin_id=account.id, action='staff.password_reset_requested', detail='Reset link emailed'))
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.warning('Password reset request could not be processed.')


def notify_changed(kind, account_id):
    try:
        account = db.session.get(KINDS[kind]['model'], account_id)
        if account:
            send(kind, 'changed', account)
            db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.warning('Password-changed notice could not be recorded.')


def after_response(response, work, *args):
    """Run work once the visitor already has the page, so response time doesn't depend on whether an account exists."""
    app = current_app._get_current_object()
    def run():
        with app.app_context():
            work(*args)
    response.call_on_close(run)
    return response
