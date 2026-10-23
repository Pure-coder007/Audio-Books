from app.curated_catalog import restore
from app.extensions import db
from app.models import Audiobook


def test_supplied_title_replaces_samples_and_is_preview_only(app,client):
    with app.app_context():
        original=db.session.get(Audiobook,app.config['TEST_BOOK_ID'])
        original.is_demo=True
        db.session.commit()
        book=restore(app)
        book_id=book.id
        restore(app)
        assert original.state=='archived'
        assert book.author.name=='David Mozie'
        assert book.asset('cover') and book.asset('trailer')
        assert book.asset('trailer').duration_seconds<=60
        assert db.session.scalar(db.select(db.func.count()).select_from(Audiobook).where(Audiobook.slug==book.slug))==1
    response=client.get('/books?q=5000')
    assert b'5000 Names of God' in response.data
    assert b'Test Book' not in response.data
    # The supplied title is featured without a price, so it is announced as Coming soon.
    assert b'Coming soon' in response.data
    assert b'Price pending' not in response.data
    assert b'5000 Names of God' in client.get('/featured').data
    detail=client.get('/books/5000-names-of-god')
    assert detail.status_code==200
    assert b'Add to cart' not in detail.data
    assert client.post(f'/cart/add/{book_id}').status_code==404


def test_priced_title_displays_pounds_even_when_sales_disabled(app, client):
    with app.app_context():
        book = db.session.get(Audiobook, app.config['TEST_BOOK_ID'])
        book.price_minor, book.currency, book.saleable = 1499, 'gbp', False
        db.session.commit()
    for path in ['/books', '/books/test-book']:
        response = client.get(path)
        assert '£14.99'.encode() in response.data
        assert b'Coming soon' not in response.data


def test_supplied_coming_soon_titles_are_featured_without_price(app, client):
    with app.app_context():
        restore(app)
        restore(app)
        for slug in ['victory-unattended', 'genius-in-the-dungeon']:
            books = db.session.scalars(db.select(Audiobook).where(Audiobook.slug == slug)).all()
            assert len(books) == 1
            book = books[0]
            assert book.coming_soon and not book.saleable and book.state == 'published'
            assert book.asset('cover') and book.author.name == 'David Mozie'
        book = db.session.scalar(db.select(Audiobook).where(Audiobook.slug == 'victory-unattended'))
        book.price_minor, book.saleable = 899, True
        db.session.commit()
        restore(app)
        assert db.session.scalar(db.select(Audiobook).where(Audiobook.slug == 'victory-unattended')).price_minor == 899
    page = client.get('/featured').data
    # Victory Unattended now has a price, so only the unpriced title stays featured.
    assert b'Genius in the Dungeon' in page and b'Victory Unattended' not in page
    detail = client.get('/books/genius-in-the-dungeon')
    assert detail.status_code == 200 and b'Coming soon' in detail.data and b'Length TBC' in detail.data


def test_supplied_childrens_titles_are_on_childrens_shelf_and_featured(app, client):
    with app.app_context():
        restore(app)
        restore(app)
        books = db.session.scalars(db.select(Audiobook).where(Audiobook.children.is_(True))).all()
        assert len({b.slug for b in books}) == len(books) >= 12
        book = db.session.scalar(db.select(Audiobook).where(Audiobook.slug == 'the-secret-of-being-kind'))
        assert book.coming_soon and not book.saleable and book.asset('cover')
        assert [c.slug for c in book.categories] == ['children']
    for path in ['/featured', '/books?collection=children', '/genres/children']:
        assert b'The Secret of Being Kind' in client.get(path).data
    assert client.get('/books/the-secret-of-being-kind').status_code == 200


def test_coming_soon_title_by_another_author_keeps_its_author(app, client):
    with app.app_context():
        restore(app)
        restore(app)
        books = db.session.scalars(db.select(Audiobook).where(Audiobook.slug == 'heritage-of-loss')).all()
        assert len(books) == 1 and books[0].coming_soon and books[0].asset('cover')
        assert books[0].author.name == 'Usman Oladipo Akanbi'
        assert not db.session.scalar(db.select(Audiobook).where(Audiobook.slug == '5000-acts-of-love'))
    page = client.get('/featured').data
    assert b'Heritage of Loss' in page and b'5000 Acts of Love' not in page
    assert b'Usman Oladipo Akanbi' in client.get('/books/heritage-of-loss').data


def test_footer_has_no_developer_credit(client):
    page = client.get('/').data
    assert b'TECHNEST' not in page and b'developer-credit' not in page
    assert b'width="1535" height="1024"' in page
