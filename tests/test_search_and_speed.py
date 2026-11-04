import json
import re
from pathlib import Path
from PIL import Image
from sqlalchemy import event
from app.extensions import db
from app.models import Audiobook, Author, Category, MediaAsset, now

STATIC = Path(__file__).resolve().parent.parent / 'app' / 'static'


def add_shelf(app, first, last):
    with app.app_context():
        for index in range(first, last):
            book = Audiobook(title=f'Shelf Book {index}', slug=f'shelf-book-{index}', author=Author(name=f'Author {index}', slug=f'author-{index}'),
                categories=[Category(name=f'Genre {index}', slug=f'genre-{index}')], synopsis='A shelf book', language='English',
                price_minor=0, currency='gbp', state='published', published_at=now(), featured=True, homepage_visible=True)
            book.media.append(MediaAsset(kind='cover', storage_key=f'cover-{index}.png', mime_type='image/png', size_bytes=1))
            db.session.add(book)
        db.session.commit()


def count_queries(app, client, path):
    statements = []
    listener = lambda conn, cursor, statement, *args: statements.append(statement)
    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', listener)
        try:
            assert client.get(path).status_code == 200
        finally:
            event.remove(db.engine, 'before_cursor_execute', listener)
    return len(statements)


def test_shelves_load_in_a_fixed_number_of_queries(app, client):
    # The database is in another region, so a query per book would add seconds to each page.
    pages = ['/', '/books', '/featured']
    add_shelf(app, 0, 3)
    small = {path: count_queries(app, client, path) for path in pages}
    add_shelf(app, 3, 12)
    assert {path: count_queries(app, client, path) for path in pages} == small
    assert small['/'] <= 6


def test_homepage_names_the_site_for_search_engines(client):
    html = client.get('/').get_data(as_text=True)
    data = json.loads(re.search(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S).group(1))
    website = next(item for item in data['@graph'] if item['@type'] == 'WebSite')
    assert website['name'] == 'MyAudioShelf' and 'My Audio Shelf' in website['alternateName']
    assert website['url'] == 'http://localhost/'
    organization = next(item for item in data['@graph'] if item['@type'] == 'Organization')
    assert organization['legalName'] == 'MyAudioShelf Ltd'


def test_every_page_has_one_link_preview(app, client):
    assert Image.open(STATIC / 'images' / 'app' / 'share.jpg').size == (1200, 630)
    for path, title, image in [('/', 'MyAudioShelf — Stories worth listening to', 'share.jpg'),
            ('/books/test-book', 'Test Book', '/static/covers/placeholder.svg'), ('/about', 'About MyAudioShelf — MyAudioShelf', 'share.jpg')]:
        html = client.get(path).get_data(as_text=True)
        assert re.findall(r'<meta property="og:title" content="([^"]*)"', html) == [title]
        images = re.findall(r'<meta property="og:image" content="([^"]*)"', html)
        assert len(images) == 1 and images[0].endswith(image)
