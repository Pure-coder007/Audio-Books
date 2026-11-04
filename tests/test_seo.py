import json
import re
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from PIL import Image
from app import create_app
from app.content.articles import ARTICLES
from app.extensions import db
from app.models import Audiobook, Author, Category, MediaAsset, now
from app.seo import PLACEHOLDER_SYNOPSIS


def schema(html):
    items = []
    for block in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        data = json.loads(block)
        items += data.get('@graph', [data])
    return items


def of_type(items, kind):
    return next(item for item in items if kind == item['@type'] or kind in item['@type'])


def robots_and_canonical(html):
    robots = re.search(r'<meta name="robots" content="([^"]*)"', html)
    canonical = re.search(r'<link rel="canonical" href="([^"]*)"', html)
    return robots and robots.group(1), canonical and canonical.group(1)


def add_book(app, slug, **fields):
    with app.app_context():
        author = db.session.scalar(db.select(Author).where(Author.slug == 'test-author'))
        category = db.session.scalar(db.select(Category).where(Category.slug == 'fiction'))
        values = dict(title=slug.replace('-', ' ').title(), slug=slug, author=author, categories=[category], synopsis='A real description of the story.',
            state='published', published_at=now(), price_minor=999, currency='gbp', saleable=True)
        book = Audiobook(**{**values, **fields})
        db.session.add(book)
        db.session.commit()
        return book.id


def test_robots_keeps_private_areas_out_without_hiding_linked_pages(client):
    text = client.get('/robots.txt').get_data(as_text=True)
    assert 'Disallow: /checkout/' in text and 'Disallow: /library/' in text and 'Disallow: /media/private/' in text
    assert 'Sitemap: http://localhost/sitemap.xml' in text
    # Linked pages like /admin/login and /library must stay crawlable so their noindex header is seen.
    assert 'Disallow: /admin' not in text and 'Disallow: /library\n' not in text
    for path in ['/admin/login', '/library', '/cart']:
        assert client.get(path).headers['X-Robots-Tag'] == 'noindex, nofollow'


def test_sitemap_lists_only_indexable_pages_and_each_returns_200(app, client):
    add_book(app, 'placeholder-title', synopsis='An audiobook. ' + PLACEHOLDER_SYNOPSIS, price_minor=0, saleable=False, featured=True)
    xml = client.get('/sitemap.xml').get_data(as_text=True)
    urls = re.findall(r'<loc>(.*?)</loc>', xml)
    assert len(urls) == len(set(urls))
    assert 'http://localhost/books/test-book' in urls and 'http://localhost/books/placeholder-title' not in urls
    assert 'http://localhost/resources' in urls and all(f'http://localhost/resources/{slug}' in urls for slug in ARTICLES)
    assert '<image:loc>http://localhost/static/covers/placeholder.svg' in xml
    for url in urls:
        path = url.removeprefix('http://localhost')
        response = client.get(path)
        assert response.status_code == 200, path
        robots, canonical = robots_and_canonical(response.get_data(as_text=True))
        assert robots is None and canonical == url, path


def test_bookshelf_canonical_and_noindex_rules(app, client):
    for index in range(12):
        add_book(app, f'shelf-{index}')
    expectations = {'/books': (None, 'http://localhost/books'), '/books?page=2': (None, 'http://localhost/books?page=2'),
        '/books?genre=fiction': (None, 'http://localhost/genres/fiction'), '/genres/fiction': (None, 'http://localhost/genres/fiction'),
        '/books?q=&genre=&language=&sort=newest': (None, 'http://localhost/books'),
        '/books?q=shelf': ('noindex, follow', None), '/books?sort=title': ('noindex, follow', None), '/books?collection=children': ('noindex, follow', None)}
    for path, expected in expectations.items():
        assert robots_and_canonical(client.get(path).get_data(as_text=True)) == expected, path
    assert client.get('/books?page=9').status_code == 404
    # "Previous" from page 2 goes to the clean address, not to ?page=1.
    assert '<a class="button secondary" href="/books">← Previous</a>' in client.get('/books?page=2').get_data(as_text=True)
    response = client.get('/books/')
    assert response.status_code == 301 and response.headers['Location'] == '/books'
    assert client.get('/genres/fiction/?page=2').headers['Location'] == '/genres/fiction?page=2'


def test_empty_genre_is_not_indexed_or_offered(app, client):
    with app.app_context():
        db.session.add(Category(name='Horror', slug='horror'))
        db.session.commit()
    assert robots_and_canonical(client.get('/genres/horror').get_data(as_text=True))[0] == 'noindex, follow'
    assert b'/genres/horror' not in client.get('/').data


def test_genre_page_has_its_own_title_description_and_introduction(client):
    html = client.get('/genres/fiction').get_data(as_text=True)
    assert '<title>Fiction Audiobooks – Novels &amp; Stories to Hear | MyAudioShelf</title>' in html or '<title>Fiction Audiobooks – Novels & Stories to Hear | MyAudioShelf</title>' in html
    assert 'class="genre-intro"' in html and 'Fiction on MyAudioShelf is chosen for the ear' in html


def test_book_page_structured_data_matches_the_page(app, client):
    add_book(app, 'victory', title='Victory', narrator='Ada Voice', duration_minutes=95)
    with app.app_context():
        book = db.session.scalar(db.select(Audiobook).where(Audiobook.slug == 'victory'))
        book.media.append(MediaAsset(kind='trailer', storage_key='t.mp3', mime_type='audio/mpeg', size_bytes=1, duration_seconds=58))
        db.session.commit()
        book_id = book.id
    html = client.get('/books/victory').get_data(as_text=True)
    items = schema(html)
    audiobook = of_type(items, 'Audiobook')
    assert audiobook['@type'] == ['Audiobook', 'Product'] and audiobook['sku'] == book_id
    assert audiobook['offers']['price'] == '9.99' and audiobook['offers']['priceCurrency'] == 'GBP'
    assert audiobook['offers']['seller']['name'] == 'MyAudioShelf' and audiobook['brand']['name'] == 'MyAudioShelf'
    assert audiobook['readBy']['name'] == 'Ada Voice' and audiobook['duration'] == 'PT1H35M' and audiobook['author']['url'] == 'http://localhost/authors/test-author'
    assert audiobook['audio']['duration'] == 'PT58S'
    crumbs = [item['name'] for item in of_type(items, 'BreadcrumbList')['itemListElement']]
    assert crumbs == ['Home', 'Audiobooks', 'Fiction', 'Victory']
    assert '<title>Victory by Test Author – Audiobook | MyAudioShelf</title>' in html
    assert 'href="/genres/fiction"' in html and 'href="/authors/test-author"' in html and '£9.99' in html
    assert 'alt="Victory by Test Author, audiobook cover"' in html


def test_coming_soon_book_has_no_offer_or_release_date(app, client):
    add_book(app, 'soon', price_minor=0, saleable=False, featured=True)
    html = client.get('/books/soon').get_data(as_text=True)
    audiobook = of_type(schema(html), 'Audiobook')
    assert audiobook['@type'] == 'Audiobook' and 'offers' not in audiobook and 'datePublished' not in audiobook
    assert '<dt>Release</dt><dd>Coming soon</dd>' in html


def test_placeholder_description_keeps_a_book_out_of_search(app, client):
    add_book(app, 'unwritten', synopsis='An audiobook by Test Author. ' + PLACEHOLDER_SYNOPSIS, price_minor=0, saleable=False, featured=True)
    assert robots_and_canonical(client.get('/books/unwritten').get_data(as_text=True)) == ('noindex, follow', None)
    assert robots_and_canonical(client.get('/books/test-book').get_data(as_text=True)) == (None, 'http://localhost/books/test-book')


def test_author_pages(app, client):
    with app.app_context():
        db.session.add(Author(name='Sample Author', slug='sample-author', bio='A fictional profile.'))
        db.session.commit()
    assert client.get('/authors/sample-author').status_code == 404
    html = client.get('/authors/test-author').get_data(as_text=True)
    page = of_type(schema(html), 'ProfilePage')
    assert page['mainEntity']['@type'] == 'Person' and page['mainEntity']['name'] == 'Test Author'
    assert 'Test Author has 1 audiobook on MyAudioShelf' in html and 'href="/genres/fiction"' in html
    assert '<title>Test Author Audiobooks | MyAudioShelf</title>' in html


def test_main_pages_have_unique_titles_and_descriptions(client):
    paths = ['/', '/books', '/featured', '/production', '/contact', '/resources', '/genres/fiction', '/books/test-book', '/authors/test-author',
        '/about', '/services', '/immersive-audio', '/children', '/originals', '/innovation', '/accessibility', '/privacy', '/terms']
    paths += [f'/resources/{slug}' for slug in ARTICLES]
    titles, descriptions = {}, {}
    for path in paths:
        html = client.get(path).get_data(as_text=True)
        titles[path] = re.search(r'<title>(.*?)</title>', html, re.S).group(1)
        descriptions[path] = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
        assert 50 <= len(descriptions[path]) <= 165, (path, len(descriptions[path]))
        assert len(re.findall(r'<h1[\s>]', html)) == 1, path
    assert len(set(titles.values())) == len(paths) and len(set(descriptions.values())) == len(paths)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.images = [], []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href', '').startswith('/'):
            self.links.append(attrs['href'].split('#')[0])
        if tag == 'img':
            self.images.append(attrs)


def test_internal_links_resolve_and_images_are_sized(app, client):
    # Books the guides link to by name; on the live shelf these are real titles.
    for slug in {slug for article in ARTICLES.values() for kind, body in article['body'] for slug in re.findall(r'href="/books/([^"]+)"', str(body))}:
        add_book(app, slug)
    seen, queue = set(), ['/']
    while queue:
        path = queue.pop()
        if path in seen or path.startswith(('/admin', '/library/', '/checkout', '/media/')) or len(seen) > 250:
            continue
        seen.add(path)
        response = client.get(path)
        assert response.status_code in {200, 301, 302}, path
        if response.mimetype == 'text/html':
            parser = Links()
            parser.feed(response.get_data(as_text=True))
            queue += [link for link in parser.links if link]
            for image in parser.images:
                assert image.get('width') and image.get('height') and 'alt' in image, (path, image)
    assert {'/resources', '/production', '/genres/fiction', '/authors/test-author'} <= seen


def test_cover_variants_are_small_webp_files(app, client):
    with app.app_context():
        book = db.session.get(Audiobook, app.config['TEST_BOOK_ID'])
        image = BytesIO()
        Image.new('RGB', (1600, 2400), (40, 90, 60)).save(image, 'JPEG')
        (Path(app.config['MEDIA_ROOT']) / 'cover.jpg').write_bytes(image.getvalue())
        book.media.append(MediaAsset(id='c' * 32, kind='cover', storage_key='cover.jpg', mime_type='image/jpeg', size_bytes=len(image.getvalue())))
        db.session.commit()
    response = client.get('/media/public/' + 'c' * 32 + '?w=360')
    assert response.status_code == 200 and response.mimetype == 'image/webp' and 'max-age=2592000' in response.headers['Cache-Control']
    assert Image.open(BytesIO(response.data)).size == (360, 540)
    assert client.get('/media/public/' + 'c' * 32 + '?w=500').status_code == 404
    assert client.get('/media/public/' + 'b' * 32 + '?w=360').status_code == 404
    html = client.get('/books/test-book').get_data(as_text=True)
    assert f'srcset="/media/public/{"c" * 32}?w=360 360w, /media/public/{"c" * 32}?w=720 720w"' in html


def test_static_files_are_versioned_and_cached_for_a_year(client):
    css = re.search(r'href="(/static/css/main\.css\?v=[0-9a-f]{10})"', client.get('/').get_data(as_text=True)).group(1)
    assert client.get(css).headers['Cache-Control'] == 'public, max-age=31536000'
    assert 'max-age=31536000' not in client.get('/static/css/main.css').headers.get('Cache-Control', '')


def test_social_tags_on_book_and_article_pages(client):
    html = client.get('/books/test-book').get_data(as_text=True)
    assert '<meta name="twitter:title" content="Test Book by Test Author">' in html and '<meta property="og:type" content="book">' in html
    slug = next(iter(ARTICLES))
    html = client.get(f'/resources/{slug}').get_data(as_text=True)
    article = of_type(schema(html), 'Article')
    assert article['headline'] == ARTICLES[slug]['title'] and article['publisher']['name'] == 'MyAudioShelf'
    assert '<meta property="og:type" content="article">' in html


def test_google_analytics_is_off_until_configured(client):
    html = client.get('/').get_data(as_text=True)
    assert 'analytics.js' not in html and 'googletagmanager' not in client.get('/').headers['Content-Security-Policy']
    assert 'We do not currently use advertising' in client.get('/cookies').get_data(as_text=True)


def test_google_analytics_needs_consent_and_is_described(app, tmp_path):
    app.config['GA_MEASUREMENT_ID'] = 'G-TEST1234'
    client = app.test_client()
    response = client.get('/')
    html = response.get_data(as_text=True)
    assert '<meta name="analytics-id" content="G-TEST1234">' in html and 'js/analytics.js' in html and 'data-consent-open' in html
    # The tag itself is never in the page: analytics.js adds it only after the visitor accepts.
    assert 'googletagmanager.com/gtag' not in html
    assert re.search(r"script-src [^;]*https://www\.googletagmanager\.com", response.headers['Content-Security-Policy'])
    assert '_ga' in client.get('/cookies').get_data(as_text=True)
    client.post('/contact', data={'name': 'A', 'email': 'a@example.com', 'message': 'Hello', 'enquiry_type': 'general', 'consent': '1'})
    assert '<meta name="analytics-event" content="generate_lead">' in client.get('/contact').get_data(as_text=True)


def test_invalid_analytics_id_is_rejected(tmp_path):
    try:
        create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SECRET_KEY': 'x' * 40, 'GA_MEASUREMENT_ID': 'UA-123', 'MEDIA_ROOT': str(tmp_path)})
    except RuntimeError as error:
        assert 'GA_MEASUREMENT_ID' in str(error)
    else:
        raise AssertionError('An invalid measurement ID should stop the app from starting.')


def test_new_book_does_not_erase_an_authors_biography(app, admin_client):
    with app.app_context():
        db.session.scalar(db.select(Author).where(Author.slug == 'test-author')).bio = 'Writes stories for the ear.'
        db.session.commit()
    admin_client.post('/admin/books/new', data={'title': 'Another', 'author_name': 'Test Author', 'author_bio': '', 'synopsis': 'Story', 'language': 'English',
        'production_style': 'Narrated', 'state': 'draft'})
    with app.app_context():
        assert db.session.scalar(db.select(Author).where(Author.slug == 'test-author')).bio == 'Writes stories for the ear.'


def test_dashboard_lists_what_keeps_pages_out_of_search(app, admin_client):
    add_book(app, 'unwritten', synopsis=PLACEHOLDER_SYNOPSIS, price_minor=0, saleable=False, featured=True)
    html = admin_client.get('/admin/').get_data(as_text=True)
    assert 'Search readiness' in html and 'Unwritten' in html and 'Author pages without a biography' in html


def test_descriptions_end_on_a_whole_sentence_when_one_fits():
    from app.seo import summary
    first = 'Authors Gamble treats the writing life as a series of calculated bets, and shows authors how to place each one with confidence and care.'
    assert summary(first + ' Across eight chapters it tackles writer’s block and much more besides.') == first
    assert summary('Short. ' + 'word ' * 60).endswith('…')
