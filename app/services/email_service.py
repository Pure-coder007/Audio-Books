"""Branded purchase emails, delivered after payment commits via a durable outbox."""
import smtplib
import ssl
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo
from email.message import EmailMessage
from email.utils import parseaddr
import requests
from flask import current_app, has_request_context, render_template
from sqlalchemy.exc import SQLAlchemyError
from ..extensions import db
from ..models import EmailDelivery, Order, Audiobook, PurchaseEntitlement, now, uid
from .access_service import issue_magic_link

class DeliveryError(Exception):
    pass

def configured():
    if current_app.config.get('RESEND_API_KEY'):
        sender = parseaddr(current_app.config.get('RESEND_FROM_EMAIL', ''))[1]
        return bool('@' in sender and not sender.endswith('@example.com'))
    return bool(current_app.config.get('MAIL_HOST'))

def money(value, currency):
    return current_app.jinja_env.filters['money'](value, currency)

def email_content(email, link, order=None):
    """Return HTML and a readable text alternative; never expose storage credentials."""
    # Cron retries run without a browser request. Give templates and cover URL
    # generation a context rooted at the configured public website.
    if not has_request_context():
        with current_app.test_request_context(base_url=current_app.config['BASE_URL']):
            return email_content(email, link, order)
    base = current_app.config['BASE_URL']
    books = []
    if order:
        entries = [(db.session.get(Audiobook, item.book_id), item.title, money(item.price_minor, order.currency)) for item in order.items]
    else:
        purchased = db.session.scalars(db.select(Audiobook).join(PurchaseEntitlement).join(Order, PurchaseEntitlement.order_id == Order.id).where(
            PurchaseEntitlement.email == email, PurchaseEntitlement.active.is_(True), Order.status == 'paid')).all()
        entries = [(book, book.title, None) for book in purchased]
    for book, title, price in entries:
        if not book:
            continue
        books.append({'title': title, 'author': book.author.name, 'duration': book.duration_label,
            'chapters': len(book.chapters), 'price': price,
            'cover': base + book.cover_url,
            'download': link + '?download=' + book.id})
    minutes = max(1, current_app.config['MAGIC_LINK_TTL'] // 60)
    receipt = None
    if order:
        date = (order.paid_at or now()).replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Africa/Lagos'))
        receipt = {'reference': 'AS-' + order.id[:12].upper(), 'date': date.strftime('%d %b %Y'), 'total': money(order.total_minor, order.currency)}
    subject = 'Your audiobooks are ready — MyAudioShelf' if order else 'Your secure listening link — MyAudioShelf'
    html = render_template('emails/access.html', subject=subject, books=books, order=receipt,
        base_url=base, logo_url=base + '/static/images/brand/aud-logo.png', access_url=link,
        library_url=base + '/library', contact_url=base + '/contact', expiry_minutes=minutes)
    text = ['Thank you for your purchase.' if order else 'Welcome back to MyAudioShelf.', '',
            'Your audiobooks are ready to stream or download. No account or password needed.', '']
    if receipt:
        text += [f"Order {receipt['reference']} · {receipt['date']}", f"Total paid: {receipt['total']}", '']
    for book in books:
        text += [book['title'] + ' — ' + book['author'], 'Download the complete audiobook: ' + book['download'], '']
    text += ['Open my audiobooks: ' + link, '', f'This secure, single-use link expires in {minutes} minutes.',
             'Request a fresh link anytime: ' + base + '/library',
             'Chapter-based books download as one ordered ZIP with every chapter.', '',
             'Keep this access link private. Need help? ' + base + '/contact', '', 'MyAudioShelf · Your books, your pace.']
    return subject, '\n'.join(text), html

def refresh_content(item, order=None):
    link = issue_magic_link(item.recipient)
    item.subject, item.body, item.html_body = email_content(item.recipient, link, order)
    item.link_expires_at = now() + timedelta(seconds=current_app.config['MAGIC_LINK_TTL'])
    item.delivery_key = uid()

def queue_access_email(email, order=None):
    item = EmailDelivery(recipient=email, order_id=order.id if order else None)
    refresh_content(item, order)
    db.session.add(item)
    return item

def send_email(item):
    if current_app.config.get('RESEND_API_KEY'):
        if not configured():
            raise DeliveryError('Set RESEND_FROM_EMAIL to an address on your verified Resend domain.')
        sender = current_app.config['RESEND_FROM_EMAIL']
        payload = {'from': sender, 'to': [item.recipient], 'subject': item.subject,
                   'text': item.body, 'html': item.html_body}
        reply = current_app.config.get('RESEND_REPLY_TO')
        if reply:
            payload['reply_to'] = reply
        try:
            with requests.post('https://api.resend.com/emails', json=payload,
                headers={'Authorization': 'Bearer ' + current_app.config['RESEND_API_KEY'],
                         'Idempotency-Key': 'shelf-email/' + item.delivery_key},
                timeout=(5, 15), allow_redirects=False) as response:
                if response.status_code not in (200, 201):
                    raise DeliveryError(f'Resend rejected request (HTTP {response.status_code}).')
                result = response.json()
                if not isinstance(result, dict) or not result.get('id'):
                    raise DeliveryError('Resend returned no message identifier.')
                return result['id']
        except (requests.RequestException, ValueError) as error:
            raise DeliveryError('Resend connection failed; retry pending.') from error
    msg = EmailMessage()
    msg['Subject'], msg['From'], msg['To'] = item.subject, current_app.config['MAIL_FROM'], item.recipient
    msg.set_content(item.body)
    msg.add_alternative(item.html_body, subtype='html')
    try:
        with smtplib.SMTP(current_app.config['MAIL_HOST'], current_app.config['MAIL_PORT'], timeout=15) as smtp:
            if current_app.config['MAIL_USE_TLS']:
                smtp.starttls(context=ssl.create_default_context())
            if current_app.config['MAIL_USERNAME']:
                smtp.login(current_app.config['MAIL_USERNAME'], current_app.config['MAIL_PASSWORD'])
            smtp.send_message(msg)
        return None
    except (OSError, smtplib.SMTPException) as error:
        raise DeliveryError('SMTP delivery failed; retry pending.') from error

def deliver_pending(ids=None, limit=100):
    """Claim messages atomically. Provider failures never undo a verified purchase."""
    if not configured():
        return 0
    query = db.select(EmailDelivery.id).where(EmailDelivery.status == 'queued',
        db.or_(EmailDelivery.claimed_until.is_(None), EmailDelivery.claimed_until < now())
        ).order_by(EmailDelivery.created_at, EmailDelivery.id).limit(limit)
    if ids is not None:
        query = query.where(EmailDelivery.id.in_(ids))
    candidates = db.session.scalars(query).all()
    sent = 0
    for identity in candidates:
        claim = now() + timedelta(minutes=2)
        result = db.session.execute(db.update(EmailDelivery).where(EmailDelivery.id == identity,
            EmailDelivery.status == 'queued', db.or_(EmailDelivery.claimed_until.is_(None), EmailDelivery.claimed_until < now())).values(claimed_until=claim))
        db.session.commit()
        if result.rowcount != 1:
            continue
        item = db.session.get(EmailDelivery, identity)
        order = db.session.get(Order, item.order_id) if item.order_id else None
        if item.order_id and (not order or order.status != 'paid'):
            item.status, item.claimed_until = 'cancelled', None
            item.body, item.html_body = '[Cancelled; access link removed]', None
            db.session.commit()
            continue
        # Preserve the exact payload/key during short retries. Refresh expired links
        # with a new idempotency key, so recovered messages contain usable access.
        if not item.html_body or not item.link_expires_at or item.link_expires_at < now() + timedelta(minutes=2):
            refresh_content(item, order)
            db.session.commit()
        try:
            item.provider_message_id = send_email(item)
            item.status, item.sent_at, item.last_error = 'sent', now(), None
            item.body, item.html_body = '[Submitted to email provider; access link removed]', None
            sent += 1
        except DeliveryError as error:
            item.last_error = str(error)[:100]
            current_app.logger.warning('Email delivery retained for retry (id=%s).', identity)
        item.attempts += 1
        item.claimed_until = None
        db.session.commit()
    return sent

def deliver_safely(item_id):
    try:
        return deliver_pending(ids=[item_id], limit=1)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.warning('Email outbox unavailable; purchase access is preserved.')
        return 0
