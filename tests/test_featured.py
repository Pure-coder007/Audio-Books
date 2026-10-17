import io
from app.extensions import db
from app.models import Audiobook
from test_admin import metadata, cover_bytes


def coming_soon_form(app, **changes):
    data = metadata(app, **{'state': 'published', 'price': '', 'featured': 'on', **changes})
    data.pop('saleable')
    data['cover'] = (io.BytesIO(cover_bytes()), 'cover.png')
    return data


def make_test_book_coming_soon(app):
    with app.app_context():
        book = db.session.get(Audiobook, app.config['TEST_BOOK_ID'])
        book.featured, book.price_minor, book.saleable = True, 0, False
        db.session.commit()


def test_nav_links_to_featured_page_with_empty_state(client):
    home = client.get('/').data
    assert b'href="/featured"' in home and b'>Featured</a>' in home
    response = client.get('/featured')
    assert response.status_code == 200
    assert b'Fresh picks are on their way.' in response.data
    assert b'/featured' in client.get('/sitemap.xml').data


def test_featured_title_without_price_publishes_as_coming_soon(admin_client, app):
    response = admin_client.post('/admin/books/new', data=coming_soon_form(app))
    assert response.status_code == 302
    with app.app_context():
        book = db.session.scalar(db.select(Audiobook).where(Audiobook.slug == 'new-real-title'))
        assert book.state == 'published' and book.featured and book.price_minor == 0
        assert book.coming_soon and not book.saleable
        book_id = book.id
    edit = admin_client.get(f'/admin/books/{book_id}/edit').data
    assert b'on the Featured shelf as Coming soon' in edit
    page = admin_client.get('/featured').data
    assert b'New Real Title' in page and b'id="coming-soon"' in page
    detail = admin_client.get('/books/new-real-title').data
    assert b'coming-soon-tag detail-price' in detail and b'Notify me when it' in detail
    assert b'name="buy_now"' not in detail
    assert admin_client.post(f'/cart/add/{book_id}').status_code == 404


def test_unfeatured_title_without_price_still_needs_a_price(admin_client, app):
    data = coming_soon_form(app)
    data.pop('featured')
    response = admin_client.post('/admin/books/new', data=data)
    assert response.status_code == 200
    assert b'id="price-error"' in response.data and b'tick Featured' in response.data
    with app.app_context():
        assert db.session.scalar(db.select(Audiobook).where(Audiobook.slug == 'new-real-title')) is None


def test_adding_a_price_later_opens_sales(admin_client, app):
    make_test_book_coming_soon(app)
    page = admin_client.get('/featured').data
    assert b'id="coming-soon"' in page and b'Test Book' in page
    data = metadata(app, title='Test Book', author_name='Test Author', state='published', price='9.99', featured='on')
    data.pop('saleable')
    data['cover'] = (io.BytesIO(cover_bytes()), 'cover.png')
    assert admin_client.post(f'/admin/books/{app.config["TEST_BOOK_ID"]}/edit', data=data).status_code == 302
    with app.app_context():
        book = db.session.get(Audiobook, app.config['TEST_BOOK_ID'])
        assert book.price_minor == 999 and book.saleable and not book.coming_soon
    # A priced book leaves the Featured page and is sold from the bookshelf.
    page = admin_client.get('/featured').data
    assert b'Test Book' not in page and b'Fresh picks are on their way.' in page
    assert '£9.99'.encode() in admin_client.get('/books').data
    assert admin_client.post(f'/cart/add/{app.config["TEST_BOOK_ID"]}').status_code == 302


def test_priced_coming_soon_title_still_requires_audio(admin_client, app):
    response = admin_client.post('/admin/books/new', data=coming_soon_form(app, price='4.99'))
    assert response.status_code == 200
    for field in ['trailer', 'full']:
        assert f'id="{field}-error"'.encode() in response.data


def test_admin_books_list_filters_coming_soon(admin_client, app):
    assert b'Test Book' not in admin_client.get('/admin/books?view=coming_soon').data.split(b'<tbody>')[1]
    make_test_book_coming_soon(app)
    listing = admin_client.get('/admin/books?view=coming_soon').data
    assert b'Test Book' in listing and b'coming-soon-status' in listing


def test_services_menu_lists_read_only_services(client):
    page = client.get('/books').data.decode()
    menu = page.split('nav-services-menu', 1)[1].split('</details>', 1)[0]
    for title in ['Audio Book Review', 'Production', 'Translation', 'Publishing']:
        assert title in menu
    assert '<a ' not in menu and 'We review books, make them audio, and publish them.' in menu
