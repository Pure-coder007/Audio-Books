import io
import wave
from pathlib import Path
import pytest
from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import db
from app.models import AdminUser, Author, Category, Audiobook, MediaAsset, Order, OrderItem, PurchaseEntitlement, uid, now

@pytest.fixture
def app(tmp_path):
    app = create_app({'TESTING':True, 'SECRET_KEY':'test-secret-only-0123456789abcdefghijkl',
        'SQLALCHEMY_DATABASE_URI':'sqlite://', 'MEDIA_ROOT':str(tmp_path/'media'),
        'WTF_CSRF_ENABLED':False, 'RATELIMIT_ENABLED':False, 'DEMO_MODE':False,
        'PRODUCTION':False, 'STRIPE_SECRET_KEY':'sk_test_fixture', 'STRIPE_WEBHOOK_SECRET':'whsec_fixture',
        'MAIL_HOST':'', 'RESEND_API_KEY':'', 'BASE_URL':'http://localhost', 'BUNNY_STORAGE_ZONE':'', 'BUNNY_STORAGE_ACCESS_KEY':'', 'BUNNY_STORAGE_ENDPOINT':'https://storage.bunnycdn.com'})
    with app.app_context():
        db.create_all()
        author=Author(name='Test Author', slug='test-author')
        category=Category(name='Fiction',slug='fiction')
        book=Audiobook(title='Test Book',slug='test-book',author=author,narrator='Test Narrator',
            synopsis='A test synopsis',language='English',price_minor=450000,currency='ngn',
            duration_minutes=60,state='published',published_at=now(),categories=[category])
        admin=AdminUser(email='owner@example.com',password_hash=generate_password_hash('test-password-long'),role='owner')
        db.session.add_all([book,admin]);db.session.flush()
        root=Path(app.config['MEDIA_ROOT']);root.mkdir()
        audio=wav_bytes()
        (root/'private.wav').write_bytes(audio)
        (root/'trailer.wav').write_bytes(audio)
        book.media.append(MediaAsset(id='a'*32,kind='full',storage_key='private.wav',mime_type='audio/wav',size_bytes=len(audio),duration_seconds=2))
        book.media.append(MediaAsset(id='b'*32,kind='trailer',storage_key='trailer.wav',mime_type='audio/wav',size_bytes=len(audio),duration_seconds=2))
        db.session.commit()
        app.config['TEST_BOOK_ID']=book.id
        app.config['TEST_ADMIN_ID']=admin.id
        app.config['TEST_ADMIN_VERSION']=admin.session_version
    yield app
    with app.app_context():
        db.session.remove();db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def admin_client(client, app):
    with client.session_transaction() as session:
        session['admin_id']=app.config['TEST_ADMIN_ID']
        session['admin_version']=app.config['TEST_ADMIN_VERSION']
    return client

def wav_bytes(seconds=2):
    stream=io.BytesIO()
    with wave.open(stream,'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(8000);audio.writeframes(b'\x00\x00' * int(seconds * 8000))
    return stream.getvalue()

@pytest.fixture
def paid_order(app):
    with app.app_context():
        book=db.session.get(Audiobook,app.config['TEST_BOOK_ID'])
        order=Order(email='buyer@example.com',total_minor=book.price_minor,currency='ngn',status='paid',stripe_session_id='cs_paid')
        order.items.append(OrderItem(book_id=book.id,title=book.title,price_minor=book.price_minor))
        db.session.add(order);db.session.flush()
        entitlement=PurchaseEntitlement(email=order.email,book_id=book.id,order_id=order.id)
        db.session.add(entitlement);db.session.commit()
        return order.id
