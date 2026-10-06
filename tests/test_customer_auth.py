from app.extensions import db
from app.models import Customer, EmailDelivery
from werkzeug.security import generate_password_hash


def test_login_page_and_nav(client):
    response = client.get('/login')
    assert response.status_code == 200
    assert b'autocomplete="current-password"' in response.data
    assert b'class="login-link"' not in client.get('/').data
    assert b'Create an account' not in response.data
    assert response.headers['Cache-Control'] == 'private, no-store'


def test_existing_customer_login_logout(client, app):
    with app.app_context():
        db.session.add(Customer(email='buyer@example.com', password_hash=generate_password_hash('a-long-secure-password')))
        db.session.commit()
    with client.session_transaction() as session:
        session['cart'] = [app.config['TEST_BOOK_ID']]
    assert b'Email or password is incorrect' in client.post('/login', data={'email':'buyer@example.com','password':'wrong'}, follow_redirects=True).data
    response = client.post('/login', data={'email':'BUYER@example.com','password':'a-long-secure-password'})
    assert response.location == '/library'
    with client.session_transaction() as session:
        assert session['listener_email'] == 'buyer@example.com'
        assert session['cart'] == [app.config['TEST_BOOK_ID']]
    client.post('/library/logout')
    with client.session_transaction() as session:
        assert 'listener_email' not in session


def test_registration_disabled(client, app):
    assert client.get('/register').status_code == 404
    assert client.post('/register', data={'email':'buyer@example.com','password':'attacker-password'}).status_code == 404
    with client.session_transaction() as session:
        session['listener_email'] = 'buyer@example.com'
    assert client.get('/register').status_code == 404
    assert b'/register' not in client.get('/library').data
    with app.app_context():
        assert db.session.scalar(db.select(Customer)) is None
        assert db.session.scalar(db.select(EmailDelivery)) is None
