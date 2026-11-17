from werkzeug.security import generate_password_hash
from app.extensions import db
from app.models import AuthorAccount, ProductionEnquiry

SIGNUP = {'name': 'Ada Writer', 'email': 'Ada@Example.com', 'password': 'a-long-author-password', 'plan': 'pro', 'consent': 'on'}


def test_pricing_page_lists_every_plan_and_the_trial(client):
    response = client.get('/pricing')
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    for name, price in [('Lite', '£19'), ('Author', '£39'), ('Pro Author', '£79'), ('Publisher', '£199')]:
        assert name in page and price in page
    assert '14-day free trial' in page and 'February 2027' in page
    assert '/authors/signup?plan=lite' in page
    assert '"billingDuration": "P1M"' in page or 'P1M' in page
    assert 'href="/pricing"' in client.get('/').get_data(as_text=True)
    assert '/pricing' in client.get('/sitemap.xml').get_data(as_text=True)


def test_production_page_leads_with_plans_and_keeps_the_form(client):
    page = client.get('/production').get_data(as_text=True)
    assert 'quoted individually' not in page
    assert page.index('From £19 a month') < page.index('id="project-form"')
    assert '/authors/signup' in page and 'name="manuscript"' in page


def test_signup_creates_account_and_signs_in(client, app):
    response = client.post('/authors/signup', data=SIGNUP)
    assert response.status_code == 302 and response.location.startswith('/authors/account')
    with app.app_context():
        account = db.session.scalar(db.select(AuthorAccount))
        assert account.email == 'ada@example.com' and account.plan == 'pro'
        assert account.password_hash != SIGNUP['password']
    page = client.get('/authors/account?welcome=1').get_data(as_text=True)
    assert 'Ada' in page and 'Pro Author' in page and 'Trial reserved' in page
    assert client.get('/authors/account').headers['Cache-Control'] == 'private, no-store'


def test_signup_validates_and_rejects_duplicates(client):
    bad = client.post('/authors/signup', data={**SIGNUP, 'password': 'short', 'consent': ''})
    assert bad.status_code == 400
    assert 'Use at least 10 characters' in bad.get_data(as_text=True)
    client.post('/authors/signup', data=SIGNUP)
    client.post('/authors/logout')
    again = client.post('/authors/signup', data=SIGNUP)
    assert again.status_code == 400 and 'already uses this email' in again.get_data(as_text=True)


def test_unknown_plan_falls_back_to_author(client, app):
    client.post('/authors/signup', data={**SIGNUP, 'plan': 'free-forever'})
    with app.app_context():
        assert db.session.scalar(db.select(AuthorAccount.plan)) == 'author'


def test_login_logout_and_account_requires_login(client, app):
    assert client.get('/authors/account').location.startswith('/authors/login')
    with app.app_context():
        db.session.add(AuthorAccount(name='Ben', email='ben@example.com', password_hash=generate_password_hash('ben-secure-password'), plan='lite'))
        db.session.commit()
    assert 'incorrect' in client.post('/authors/login', data={'email': 'ben@example.com', 'password': 'nope'}, follow_redirects=True).get_data(as_text=True)
    assert client.post('/authors/login', data={'email': 'BEN@example.com', 'password': 'ben-secure-password'}).location == '/authors/account'
    assert client.get('/authors/account').status_code == 200
    assert 'Author account' in client.get('/pricing').get_data(as_text=True)
    client.post('/authors/logout')
    assert client.get('/authors/account').status_code == 302


def test_login_ignores_offsite_next(client, app):
    with app.app_context():
        db.session.add(AuthorAccount(name='Ben', email='ben@example.com', password_hash=generate_password_hash('ben-secure-password')))
        db.session.commit()
    response = client.post('/authors/login', data={'email': 'ben@example.com', 'password': 'ben-secure-password', 'next': '//evil.example/'})
    assert response.location == '/authors/account'


def test_change_plan_and_password(client, app):
    client.post('/authors/signup', data=SIGNUP)
    client.post('/authors/account/plan', data={'plan': 'publisher'})
    client.post('/authors/account/plan', data={'plan': 'bogus'})
    with app.app_context():
        assert db.session.scalar(db.select(AuthorAccount.plan)) == 'publisher'
    other = app.test_client()
    other.post('/authors/login', data={'email': SIGNUP['email'], 'password': SIGNUP['password']})
    client.post('/authors/account/password', data={'current_password': SIGNUP['password'], 'new_password': 'a-brand-new-password'})
    assert client.get('/authors/account').status_code == 200
    assert other.get('/authors/account').status_code == 302
    assert client.post('/authors/login', data={'email': SIGNUP['email'], 'password': 'a-brand-new-password'}).status_code == 302


def test_project_sent_while_signed_in_appears_in_account(client, app):
    client.post('/authors/signup', data=SIGNUP)
    assert 'value="Ada Writer"' in client.get('/production').get_data(as_text=True)
    response = client.post('/production', data={'name': 'Ada Writer', 'email': 'ada@example.com', 'title': 'The Long Tide',
        'message': 'A novel about the sea.', 'consent': 'on', 'preferred_style': 'Enhanced', 'word_count': '82000'})
    assert response.location == '/authors/account#projects'
    page = client.get('/authors/account').get_data(as_text=True)
    assert 'The Long Tide' in page and '82,000 words' in page and 'Received' in page
    with app.app_context():
        assert db.session.scalar(db.select(ProductionEnquiry)).author_account.email == 'ada@example.com'


def test_admin_lists_author_accounts(admin_client):
    admin_client.post('/authors/signup', data=SIGNUP)
    page = admin_client.get('/admin/authors').get_data(as_text=True)
    assert 'ada@example.com' in page and 'Pro Author' in page
    assert 'Author accounts' in admin_client.get('/admin/').get_data(as_text=True)
