import xml.etree.ElementTree as ET
from app.extensions import db
from app.models import Audiobook, Author, Category, Chapter, MediaAsset, now

G = '{http://base.google.com/ns/1.0}'


def shelf_book(slug, title, price, currency='gbp', saleable=True, full=True):
    book = Audiobook(title=title, slug=slug, author=Author(name='Ada Writer', slug=f'ada-{slug}'), categories=[Category(name=f'Drama {slug}', slug=f'drama-{slug}')],
        synopsis='A story told aloud.', language='English', price_minor=price, currency=currency, state='published',
        published_at=now(), saleable=saleable, featured=price == 0)
    book.media.append(MediaAsset(kind='cover', storage_key=f'{slug}.png', mime_type='image/png', size_bytes=1))
    if full:
        book.media.append(MediaAsset(kind='full', storage_key=f'{slug}.mp3', mime_type='audio/mpeg', size_bytes=1))
    return book


def test_feed_lists_only_audiobooks_checkout_will_sell(app, client):
    with app.app_context():
        on_sale = shelf_book('on-sale', 'Love & Victory', 1199)
        unfinished = shelf_book('unfinished', 'Half Told', 999, full=False)
        chaptered = shelf_book('chaptered', 'Told in Parts', 899, full=False)
        chaptered.chapters.append(Chapter(title='Chapter 1', position=1, media=MediaAsset(book=chaptered, kind='chapter', storage_key='c1.mp3', mime_type='audio/mpeg', size_bytes=1)))
        db.session.add_all([on_sale, unfinished, chaptered, shelf_book('soon', 'Coming Soon', 0, saleable=False),
            shelf_book('naira', 'Priced in Naira', 450000, currency='ngn'), shelf_book('not-for-sale', 'Not For Sale', 799, saleable=False)])
        db.session.commit()
        sale_id, chaptered_id = on_sale.id, chaptered.id
    response = client.get('/merchant-feed.xml')
    assert response.status_code == 200 and response.mimetype == 'application/xml'
    items = ET.fromstring(response.data).findall('channel/item')
    # Sorted by title: the audio-less, unpriced, naira and not-for-sale titles are left out.
    assert [item.findtext(f'{G}id') for item in items] == [sale_id, chaptered_id]
    item = items[0]
    assert item.findtext(f'{G}title') == 'Love & Victory – audiobook by Ada Writer'
    assert item.findtext(f'{G}product_type') == 'Audiobooks > Drama on-sale'
    assert item.findtext(f'{G}price') == '11.99 GBP' and item.findtext(f'{G}availability') == 'in_stock'
    assert item.findtext(f'{G}link') == 'http://localhost/books/on-sale'
    assert item.findtext(f'{G}image_link').startswith('http://localhost/media/public/')
    assert item.findtext(f'{G}identifier_exists') == 'no' and item.findtext(f'{G}google_product_category') == '543541'
    assert item.findtext(f'{G}shipping/{G}price') == '0.00 GBP'
