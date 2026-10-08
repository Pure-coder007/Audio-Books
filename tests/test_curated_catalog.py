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
    response=client.get('/books')
    assert b'5000 Names of God' in response.data
    assert b'Test Book' not in response.data
    assert b'Price pending' in response.data
    assert b'Coming soon' not in response.data
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
