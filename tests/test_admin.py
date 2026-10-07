import io
from PIL import Image
from app.extensions import db
from app.models import Audiobook, MediaAsset, Category, AdminUser, Chapter, AuditLog, ProductionEnquiry, NewsletterSubscriber
from app.services.media_service import store_upload
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash
from conftest import wav_bytes
import pytest

def metadata(app, **changes):
    with app.app_context():category=db.session.scalar(db.select(Category)).id
    data={'title':'New Real Title','slug':'new-real-title','author_name':'Real Author','narrator':'Real Narrator',
        'synopsis':'A real synopsis','language':'English','production_style':'Narrated','price':'3500.50',
        'currency':'ngn','duration_minutes':'120','state':'draft','categories':str(category),'saleable':'on','homepage_visible':'on'}
    data.update(changes);return data

def cover_bytes():
    buffer=io.BytesIO();Image.new('RGB',(360,540),'green').save(buffer,format='PNG');return buffer.getvalue()

def test_admin_auth_required(client):
    assert client.get('/admin/').status_code==302
    assert client.post('/admin/books/new').status_code==302

def test_admin_screens_render(admin_client):
    for path in ['/admin/','/admin/books','/admin/books/new','/admin/books/1/edit','/admin/books/1/preview','/admin/categories','/admin/orders','/admin/enquiries','/admin/staff','/admin/audit','/admin/outbox']:
        assert admin_client.get(path).status_code==200,path

def test_staff_roles_are_enforced(client,app):
    with app.app_context():
        user=AdminUser(email='support@example.com',password_hash=generate_password_hash('test-password-long'),role='support')
        db.session.add(user);db.session.commit();user_id=user.id;version=user.session_version
    with client.session_transaction() as session:session['admin_id']=user_id;session['admin_version']=version
    assert client.post('/admin/books/new',data={}).status_code==403
    assert client.get('/admin/staff').status_code==403
    assert client.get('/admin/orders').status_code==200

def test_disabled_staff_session_is_invalidated(admin_client,app):
    with app.app_context():user=db.session.get(AdminUser,app.config['TEST_ADMIN_ID']);user.active=False;db.session.commit()
    assert admin_client.get('/admin/').status_code==302

def test_create_draft_and_publish_with_required_assets(admin_client,app):
    data=metadata(app)
    assert admin_client.post('/admin/books/new',data=data).status_code==302
    with app.app_context():book=db.session.scalar(db.select(Audiobook).where(Audiobook.slug=='new-real-title'));book_id=book.id;assert book.state=='draft'
    data=metadata(app,state='published')
    data.update(cover=(io.BytesIO(cover_bytes()),'cover.png'),trailer=(io.BytesIO(wav_bytes()),'trailer.wav'),full=(io.BytesIO(wav_bytes()),'full.wav'))
    response=admin_client.post(f'/admin/books/{book_id}/edit',data=data,content_type='multipart/form-data')
    assert response.status_code==302
    with app.app_context():
        book=db.session.get(Audiobook,book_id);assert book.state=='published';assert book.price_minor==350050
        assert book.asset('cover').mime_type=='image/jpeg';assert book.asset('full')
        assert db.session.scalar(db.select(db.func.count()).select_from(AuditLog))>=2
    assert admin_client.get('/books/new-real-title').status_code==200

def test_incomplete_publication_is_rejected(admin_client,app):
    response=admin_client.post('/admin/books/new',data=metadata(app,state='published'))
    assert response.status_code==200 and b'Upload a cover' in response.data
    with app.app_context():assert db.session.scalar(db.select(Audiobook).where(Audiobook.slug=='new-real-title')) is None

def test_trailer_limit_and_fake_audio_validation(app):
    with app.app_context():
        book=db.session.get(Audiobook,app.config['TEST_BOOK_ID'])
        with pytest.raises(ValueError,match='60 seconds'):store_upload(FileStorage(stream=io.BytesIO(wav_bytes(61)),filename='long.wav'),book,'trailer')
        with pytest.raises(ValueError,match='decoded'):store_upload(FileStorage(stream=io.BytesIO(b'not-a-wave'),filename='fake.wav'),book,'full')
        with pytest.raises(ValueError):store_upload(FileStorage(stream=io.BytesIO(b'<script>'),filename='bad.svg'),book,'cover')

def test_private_audio_not_exposed_by_staff_preview_to_guests(client):
    assert client.get('/admin/media/'+'a'*32).status_code==302

def test_duplicate_slug_does_not_crash(admin_client,app):
    response=admin_client.post('/admin/books/new',data=metadata(app,slug='test-book'))
    assert response.status_code==200 and b'already in use' in response.data

@pytest.mark.parametrize('price',['1.001','-5','NaN','Infinity','word'])
def test_invalid_prices_rejected(admin_client,app,price):
    assert admin_client.post('/admin/books/new',data=metadata(app,price=price)).status_code==200
    with app.app_context():assert db.session.scalar(db.select(Audiobook).where(Audiobook.slug=='new-real-title')) is None

def test_production_and_newsletter_forms(client,app):
    assert client.post('/production',data={'name':'An Author','email':'author@example.com','title':'My Book','message':'Please produce it.','consent':'on'}).status_code==302
    assert client.post('/newsletter',data={'email':'reader@example.com','consent':'on'}).status_code==302
    with app.app_context():
        assert db.session.scalar(db.select(ProductionEnquiry)).title=='My Book'
        assert db.session.scalar(db.select(NewsletterSubscriber)).email=='reader@example.com'

def test_csrf_blocks_mutation_without_token(client,app):
    app.config['WTF_CSRF_ENABLED']=True
    assert client.post('/cart/add/1').status_code==400
    assert client.post('/admin/login',data={'email':'owner@example.com','password':'test-password-long'}).status_code==400

def test_public_pages_and_headers(client):
    for path in ['/','/books','/books?genre=fiction&q=Test','/books/test-book','/authors/test-author','/production','/cart','/library','/robots.txt','/sitemap.xml','/health']:
        assert client.get(path).status_code==200,path
    assert client.get('/library').headers['Cache-Control']=='private, no-store'
    assert client.get('/').headers['X-Content-Type-Options']=='nosniff'
    assert client.get('/not-here').status_code==404

def test_media_replacement_clears_obsolete_progress(admin_client,app,paid_order):
    from app.models import ListeningProgress
    with app.app_context():
        book=db.session.get(Audiobook,app.config['TEST_BOOK_ID'])
        db.session.add(ListeningProgress(email='buyer@example.com',book_id=book.id,media_id='a'*32,seconds=1));db.session.commit()
    data=metadata(app,title='Test Book',slug='test-book',author_name='Test Author')
    data['full']=(io.BytesIO(wav_bytes()),'replacement.wav')
    assert admin_client.post('/admin/books/1/edit',data=data,content_type='multipart/form-data').status_code==302
    with app.app_context():
        assert db.session.get(MediaAsset,'a'*32) is None
        assert db.session.scalar(db.select(ListeningProgress)).media_id is None

def test_genre_page_renders(client):
    response=client.get('/genres/fiction')
    assert response.status_code==200
    assert b'Fiction audiobooks.' in response.data
    assert client.get('/genres/missing').status_code==404
