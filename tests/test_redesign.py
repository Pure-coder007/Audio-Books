from app.extensions import db
from app.models import Audiobook


def test_homepage_shows_each_book_once_even_when_collections_overlap(client, app):
    with app.app_context():
        original = db.session.get(Audiobook, app.config['TEST_BOOK_ID'])
        original.hero = True
        original.featured = original.original = original.children = True
        original.production_style = 'Immersive'
        for index in range(2):
            db.session.add(Audiobook(title=f'Unique title {index}', slug=f'unique-{index}',
                author=original.author, state='published', homepage_visible=True,
                featured=True, original=True, children=True, production_style='Immersive',
                saleable=True, price_minor=1499))
        db.session.commit()
    response = client.get('/')
    assert response.status_code == 200
    for title in ['Test Book', 'Unique title 0', 'Unique title 1']:
        assert response.data.count(f'alt="{title} by Test Author, audiobook cover"'.encode()) == 1
    assert response.data.count(b'<article class="book-card">') == 3
    assert b'Follow your curiosity' in response.data
    assert 'What’s your kind of story?'.encode() in response.data
    assert b'genre-tile-fiction' in response.data


def test_homepage_single_book_does_not_repeat_in_shelf(client):
    response = client.get('/')
    assert response.data.count(b'alt="Test Book by Test Author, audiobook cover"') == 1
    assert response.data.count(b'<article class="book-card">') == 1
    assert b'Good stories are on their way.' not in response.data


def test_homepage_without_books_keeps_genres_and_empty_state(client, app):
    with app.app_context():
        db.session.get(Audiobook, app.config['TEST_BOOK_ID']).state = 'draft'
        db.session.commit()
    response = client.get('/')
    assert response.status_code == 200
    assert b'Good stories are on their way.' in response.data
    assert b'Follow your curiosity' in response.data


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


def test_homepage_opens_with_what_we_do_instead_of_a_book(client):
    page = client.get('/').data.decode()
    top = page.split('class="hero', 1)[1].split('</section>', 1)[0]
    assert 'What we do' in top and 'hero-feature' not in top
    for service in ['Audio book review', 'Production', 'Translation', 'Publishing']:
        assert service in top


def test_homepage_shelf_mixes_genres_instead_of_newest_only(client, app):
    from app.models import Category
    with app.app_context():
        original = db.session.get(Audiobook, app.config['TEST_BOOK_ID'])
        kids = Category(name='Kids', slug='kids')
        db.session.add(kids)
        for index in range(12):
            db.session.add(Audiobook(title=f'Kids title {index}', slug=f'kids-{index}', author=original.author,
                state='published', homepage_visible=True, categories=[kids], price_minor=0, featured=True))
        db.session.commit()
    # Twelve newer books share one genre, yet the other genre's book still gets a place.
    for _ in range(3):
        assert b'alt="Test Book by Test Author, audiobook cover"' in client.get('/').data
