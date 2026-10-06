from app.extensions import db
from app.models import Audiobook


def test_catalog_ten_per_page_and_search_reset(client, app):
    with app.app_context():
        original=db.session.get(Audiobook,app.config['TEST_BOOK_ID'])
        for n in range(11):
            db.session.add(Audiobook(title=f'Extra title {n}',slug=f'extra-{n}',author_id=original.author_id,state='published',saleable=True,price_minor=10000))
        db.session.commit()
    assert client.get('/books').data.count(b'<article class="book-card">') == 10
    assert client.get('/books?page=2').data.count(b'<article class="book-card">') == 2
    response=client.get('/books?search=all&q=Test&collection=originals&age_range=4-8',follow_redirects=True)
    assert b'Test Book' in response.data
    assert b'catalog-list' in response.data
    assert b'No stories found' not in response.data


def test_admin_book_pagination_and_signout(admin_client, app):
    with app.app_context():
        original=db.session.get(Audiobook,app.config['TEST_BOOK_ID'])
        for n in range(11):
            db.session.add(Audiobook(title=f'Draft {n}',slug=f'draft-{n}',author_id=original.author_id))
        db.session.commit()
    response=admin_client.get('/admin/books')
    assert response.status_code == 200
    assert response.data.count(b'class="admin-book-row"') == 10
    assert b'Page 1 of 2' in response.data
    assert b'class="signout-button"' in response.data
    assert admin_client.get('/admin/books?page=2').data.count(b'class="admin-book-row"') == 2
    assert admin_client.get('/admin/books?q=Test').data.count(b'class="admin-book-row"') == 1
    admin_client.post('/admin/logout')
    assert admin_client.get('/admin/books').location.endswith('/admin/login')
