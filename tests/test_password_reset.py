import re
from datetime import timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models import AuthorAccount, AdminUser, AuditLog, EmailDelivery, PasswordReset, now
from app.services import password_reset_service as resets

LINK = re.compile(r'https?://\S+/(?:authors|admin)/reset/[\w-]+')


def add_author(app, email='ada@example.com', password='old-author-password'):
    with app.app_context():
        db.session.add(AuthorAccount(name='Ada Writer', email=email, password_hash=generate_password_hash(password)))
        db.session.commit()


def latest_link(app):
    with app.app_context():
        mail = db.session.scalars(db.select(EmailDelivery).order_by(EmailDelivery.created_at.desc())).first()
        return mail, LINK.search(mail.body).group(0) if mail and LINK.search(mail.body) else None


def path(link):
    return '/' + link.split('/', 3)[3]


def test_author_reset_end_to_end(client, app):
    add_author(app)
    assert 'Forgot your password?' in client.get('/authors/login').get_data(as_text=True)
    response = client.post('/authors/forgot', data={'email': 'ADA@example.com'})
    assert response.location == '/authors/forgot?sent=1'
    response.close()
    assert 'Check your' in client.get('/authors/forgot?sent=1').get_data(as_text=True)
    mail, link = latest_link(app)
    assert mail.recipient == 'ada@example.com' and mail.status == 'development'
    assert 'Reset your MyAudioShelf password' == mail.subject
    assert 'email-logo.png' in mail.html_body and 'Choose a new password' in mail.html_body and 'Hi Ada,' in mail.html_body
    with app.app_context():
        stored = db.session.scalar(db.select(PasswordReset))
        assert link.rsplit('/', 1)[1] not in stored.token_hash  # only the hash is stored

    page = client.get(path(link))
    assert page.status_code == 200 and 'ada@example.com' in page.get_data(as_text=True)
    mismatch = client.post(path(link), data={'password': 'brand-new-password', 'confirm': 'something-else'})
    assert mismatch.status_code == 400 and 'match' in mismatch.get_data(as_text=True)
    done = client.post(path(link), data={'password': 'brand-new-password', 'confirm': 'brand-new-password'})
    assert done.location == '/authors/account'
    done.close()
    assert client.get('/authors/account').status_code == 200  # signed in after resetting
    with app.app_context():
        account = db.session.scalar(db.select(AuthorAccount))
        assert check_password_hash(account.password_hash, 'brand-new-password')
        notice = db.session.scalars(db.select(EmailDelivery).order_by(EmailDelivery.created_at.desc())).first()
        assert notice.subject == 'Your MyAudioShelf password was changed'
    assert client.get(path(link)).status_code == 410  # single use


def test_unknown_email_looks_the_same_and_sends_nothing(client, app):
    response = client.post('/authors/forgot', data={'email': 'nobody@example.com'})
    assert response.location == '/authors/forgot?sent=1'
    response.close()
    with app.app_context():
        assert db.session.scalar(db.select(EmailDelivery)) is None
        assert db.session.scalar(db.select(PasswordReset)) is None


def test_expired_and_bogus_links_are_refused(client, app):
    add_author(app)
    client.post('/authors/forgot', data={'email': 'ada@example.com'}).close()
    _, link = latest_link(app)
    with app.app_context():
        db.session.scalar(db.select(PasswordReset)).expires_at = now() - timedelta(seconds=1)
        db.session.commit()
    expired = client.get(path(link))
    assert expired.status_code == 410 and 'expired' in expired.get_data(as_text=True)
    assert client.post(path(link), data={'password': 'brand-new-password', 'confirm': 'brand-new-password'}).status_code == 410
    assert client.get('/authors/reset/not-a-real-token').status_code == 410


def test_new_link_retires_the_old_one_and_resends_are_spaced(client, app):
    add_author(app)
    client.post('/authors/forgot', data={'email': 'ada@example.com'}).close()
    client.post('/authors/forgot', data={'email': 'ada@example.com'}).close()
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(PasswordReset)) == 1
        db.session.scalar(db.select(PasswordReset)).created_at = now() - timedelta(minutes=5)
        db.session.commit()
    _, first = latest_link(app)
    client.post('/authors/forgot', data={'email': 'ada@example.com'}).close()
    _, second = latest_link(app)
    assert first != second
    assert client.get(path(first)).status_code == 410
    assert client.get(path(second)).status_code == 200


def test_reset_signs_out_other_sessions(client, app):
    add_author(app)
    other = app.test_client()
    other.post('/authors/login', data={'email': 'ada@example.com', 'password': 'old-author-password'})
    assert other.get('/authors/account').status_code == 200
    client.post('/authors/forgot', data={'email': 'ada@example.com'}).close()
    _, link = latest_link(app)
    client.post(path(link), data={'password': 'brand-new-password', 'confirm': 'brand-new-password'}).close()
    assert other.get('/authors/account').status_code == 302


def test_staff_reset_end_to_end(client, app):
    assert 'Forgot your password?' in client.get('/admin/login').get_data(as_text=True)
    client.post('/admin/forgot', data={'email': 'Owner@Example.com'}).close()
    mail, link = latest_link(app)
    assert mail.recipient == 'owner@example.com' and 'Shelf studio' in mail.subject and '/admin/reset/' in link
    assert 'studio.' in mail.html_body
    short = client.post(path(link), data={'password': 'too-short', 'confirm': 'too-short'})
    assert short.status_code == 400 and '12 to 128' in short.get_data(as_text=True)
    done = client.post(path(link), data={'password': 'a-new-staff-password', 'confirm': 'a-new-staff-password'})
    assert done.location == '/admin/login'
    done.close()
    with app.app_context():
        user = db.session.get(AdminUser, app.config['TEST_ADMIN_ID'])
        assert check_password_hash(user.password_hash, 'a-new-staff-password')
        assert user.session_version != app.config['TEST_ADMIN_VERSION']
        actions = set(db.session.scalars(db.select(AuditLog.action)).all())
        assert {'staff.password_reset_requested', 'staff.password_reset'} <= actions
    assert client.post('/admin/login', data={'email': 'owner@example.com', 'password': 'a-new-staff-password'}).location == '/admin/'


def test_inactive_staff_get_no_link(client, app):
    with app.app_context():
        db.session.get(AdminUser, app.config['TEST_ADMIN_ID']).active = False
        db.session.commit()
    client.post('/admin/forgot', data={'email': 'owner@example.com'}).close()
    with app.app_context():
        assert db.session.scalar(db.select(PasswordReset)) is None


def test_author_and_staff_links_are_not_interchangeable(client, app):
    add_author(app, email='owner@example.com')
    client.post('/admin/forgot', data={'email': 'owner@example.com'}).close()
    _, link = latest_link(app)
    token = link.rsplit('/', 1)[1]
    assert client.get('/authors/reset/' + token).status_code == 410


def test_sent_email_never_keeps_the_link(app, monkeypatch):
    add_author(app)
    monkeypatch.setattr('app.services.email_service.configured', lambda: True)
    monkeypatch.setattr('app.services.email_service.send_email', lambda item: 'msg_123')
    with app.test_request_context():
        resets.request_reset('author', 'ada@example.com')
        mail = db.session.scalar(db.select(EmailDelivery))
        assert mail.status == 'sent' and mail.provider_message_id == 'msg_123'
        assert '/authors/reset/' not in mail.body and mail.html_body is None
