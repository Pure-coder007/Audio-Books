import re
from app.extensions import db
from app.models import Audiobook
from app.content.languages import SITE_LANGUAGE_GROUPS, chosen_site_language
from test_admin import metadata


def set_book(app, **fields):
    with app.app_context():
        book = db.session.get(Audiobook, app.config['TEST_BOOK_ID'])
        for name, value in fields.items():
            setattr(book, name, value)
        db.session.commit()


def test_navigation_links_to_translated_and_reviewed_books(client):
    html = client.get('/').get_data(as_text=True)
    assert '>Translated books</a>' in html and '>Reviewed books</a>' in html
    assert client.get('/translated').status_code == 200 and client.get('/reviewed').status_code == 200


def test_admin_lists_a_book_in_its_section_and_language(admin_client, app):
    response = admin_client.post('/admin/books/new', data=metadata(app, title='Histoire du Soir', language='French', section='translated'))
    assert response.status_code == 302
    with app.app_context():
        book = db.session.scalar(db.select(Audiobook).where(Audiobook.title == 'Histoire du Soir'))
        assert (book.language, book.section) == ('French', 'translated')
    form = admin_client.get(response.headers['Location']).get_data(as_text=True)
    assert '<option value="French" selected>French · Français</option>' in form and '<option value="translated" selected>Translated books</option>' in form
    assert 'Translated (French)' in admin_client.get('/admin/books?view=translated').get_data(as_text=True)


def test_admin_rejects_unknown_languages_and_sections(admin_client, app):
    html = admin_client.post('/admin/books/new', data=metadata(app, language='Klingon')).get_data(as_text=True)
    assert 'Choose the language from the list.' in html
    html = admin_client.post('/admin/books/new', data=metadata(app, section='secret')).get_data(as_text=True)
    assert 'Choose where this book is listed.' in html


def test_admin_keeps_a_language_set_before_the_list(admin_client, app):
    set_book(app, language='Pidgin English')
    edit = f"/admin/books/{app.config['TEST_BOOK_ID']}/edit"
    assert '<option selected>Pidgin English</option>' in admin_client.get(edit).get_data(as_text=True)
    assert admin_client.post(edit, data=metadata(app, title='Test Book', language='Pidgin English')).status_code == 302


def test_translated_books_filter_by_the_chosen_language(client, app):
    set_book(app, section='translated', language='French')
    everything = client.get('/translated').get_data(as_text=True)
    assert 'Test Book' in everything and 'data-language-picker' in everything and 'Select your language' in everything
    yoruba = client.get('/translated?language=French').get_data(as_text=True)
    assert 'Test Book' in yoruba and 'In French.' in yoruba and '<option class="notranslate" translate="no" value="French" selected>Français (French) · 1</option>' in yoruba
    assert '<link rel="canonical" href="http://localhost/translated?language=French">' in yoruba
    hindi = client.get('/translated?language=Hindi').get_data(as_text=True)
    assert 'Test Book' not in hindi and 'No books in Hindi yet.' in hindi and 'noindex' in hindi
    assert client.get('/translated?language=Klingon').headers['Location'].endswith('/translated')


def test_reviewed_books_page_lists_reviewed_titles(client, app):
    empty = client.get('/reviewed').get_data(as_text=True)
    assert 'Reviewed books are on their way.' in empty and 'noindex' in empty
    set_book(app, section='reviewed')
    assert 'Test Book' in client.get('/reviewed').get_data(as_text=True)
    # An English book is listed under English on the Translated page too.
    assert 'Test Book' in client.get('/translated?language=English').get_data(as_text=True)


def test_sitemap_lists_section_pages_once_they_have_books(client, app):
    set_book(app, language='French')
    sitemap = client.get('/sitemap.xml').get_data(as_text=True)
    assert '/translated' not in sitemap and '/reviewed' not in sitemap
    set_book(app, section='translated')
    assert '<loc>http://localhost/translated</loc>' in client.get('/sitemap.xml').get_data(as_text=True)
    set_book(app, language='English', section='shelf')
    assert '<loc>http://localhost/translated</loc>' in client.get('/sitemap.xml').get_data(as_text=True)


def test_every_english_book_is_listed_under_english_and_stays_on_the_shelf(client, app):
    english = client.get('/translated?language=English').get_data(as_text=True)
    assert 'Test Book' in english and 'In English.' in english
    assert 'Test Book' in client.get('/translated').get_data(as_text=True)
    assert 'Test Book' in client.get('/books').get_data(as_text=True)
    assert 'Test Book' not in client.get('/translated?language=French').get_data(as_text=True)


def test_site_language_cookie_is_validated():
    assert chosen_site_language('/en/fr') == ('fr', 'French', 'Français') and chosen_site_language('/auto/zh-CN')[0] == 'zh-CN'
    assert chosen_site_language('/en/en') is None and chosen_site_language('/en/yo') is None and chosen_site_language('/en/fr;evil') is None
    codes = [code for _, choices in SITE_LANGUAGE_GROUPS for code, _, _ in choices]
    assert {'fr', 'ar', 'zh-CN'} <= set(codes) and not {'yo', 'ig', 'ha'} & set(codes) and len(codes) == len(set(codes)) and len(codes) > 30


def test_google_translate_is_allowed_only_after_a_visitor_chooses_a_language(client):
    english = client.get('/').headers['Content-Security-Policy']
    assert 'translate.google' not in english and 'strict-dynamic' not in english
    client.set_cookie('googtrans', '/en/fr')
    french = client.get('/')
    policy = french.headers['Content-Security-Policy']
    assert re.search(r"script-src 'self' 'nonce-[^']+' 'strict-dynamic' https://translate\.google\.com", policy)
    assert re.search(r"connect-src 'self' [^;]*https://translate\.googleapis\.com", policy)
    assert 'style-src \'self\' https://translate.googleapis.com' in policy and "'unsafe-inline'" not in policy
    assert '<span>FR</span>' in french.get_data(as_text=True)
    client.set_cookie('googtrans', '/en/notalanguage')
    assert 'strict-dynamic' not in client.get('/').headers['Content-Security-Policy']


def test_admin_pages_are_never_translated(admin_client):
    admin_client.set_cookie('googtrans', '/en/fr')
    assert 'strict-dynamic' not in admin_client.get('/admin/books').headers['Content-Security-Policy']


def test_every_script_carries_the_page_nonce(client, admin_client):
    # With 'strict-dynamic' a script without the nonce would not run for visitors reading in another language.
    for html in [client.get('/').get_data(as_text=True), client.get('/translated').get_data(as_text=True), admin_client.get('/admin/books').get_data(as_text=True)]:
        tags = re.findall(r'<script\b[^>]*>', html)
        assert tags and all('nonce="' in tag for tag in tags), [tag for tag in tags if 'nonce="' not in tag]


def test_language_panel_lists_every_site_language(client):
    html = client.get('/books').get_data(as_text=True)
    assert 'data-site-language-dialog' in html and 'Nigerian languages' not in html
    assert 'data-language="fr"' in html and 'data-language="ar"' in html and 'data-language="yo"' not in html
    assert 'Google' not in html.split('data-site-language-dialog', 1)[1].split('</dialog>', 1)[0]
    assert 'Site translation</h2>' in client.get('/cookies').get_data(as_text=True).split('id="section-4"')[1].split('</section>')[0]


def test_translation_announcement_is_only_on_the_homepage(client):
    home = client.get('/').get_data(as_text=True)
    assert 'data-translation-promo' in home and 'js/promo.js' in home and 'href="/translated" data-promo-go' in home
    assert 'data-translation-promo' not in client.get('/books').get_data(as_text=True)


def test_admin_unpublishes_and_republishes_a_book(admin_client, app):
    book_id = app.config['TEST_BOOK_ID']
    response = admin_client.post(f'/admin/books/{book_id}/visibility', data={'action': 'unpublish', 'next': '/admin/books'})
    assert response.headers['Location'].endswith('/admin/books')
    with app.app_context():
        assert db.session.get(Audiobook, book_id).state == 'draft'
    assert admin_client.get('/books/test-book').status_code == 404
    # The fixture book has no cover, so publishing sends the editor to fix it first.
    response = admin_client.post(f'/admin/books/{book_id}/visibility', data={'action': 'publish'})
    assert response.headers['Location'].endswith(f'/admin/books/{book_id}/edit')
    with app.app_context():
        assert db.session.get(Audiobook, book_id).state == 'draft'
    listing = admin_client.get('/admin/books').get_data(as_text=True)
    assert '>Publish</button>' in listing and f'/admin/books/{book_id}/delete' in listing


def test_admin_deletes_a_book_after_confirming(admin_client, app):
    admin_client.post('/admin/books/new', data=metadata(app, title='Delete Me'))
    with app.app_context():
        book_id = db.session.scalar(db.select(Audiobook.id).where(Audiobook.title == 'Delete Me'))
    confirm = admin_client.get(f'/admin/books/{book_id}/delete').get_data(as_text=True)
    assert 'Delete “Delete Me” permanently?' in confirm
    with app.app_context():
        assert db.session.get(Audiobook, book_id) is not None
    assert admin_client.post(f'/admin/books/{book_id}/delete').headers['Location'].endswith('/admin/books')
    with app.app_context():
        assert db.session.get(Audiobook, book_id) is None


def test_a_bought_book_cannot_be_deleted(admin_client, app, paid_order):
    book_id = app.config['TEST_BOOK_ID']
    page = admin_client.get(f'/admin/books/{book_id}/delete').get_data(as_text=True)
    assert 'This book can’t be deleted.' in page and 'Unpublish instead' in page
    admin_client.post(f'/admin/books/{book_id}/delete')
    with app.app_context():
        assert db.session.get(Audiobook, book_id) is not None


def test_coming_soon_childrens_books_are_listed_under_english(client, app):
    set_book(app, children=True, featured=True, price_minor=0, saleable=False)
    english = client.get('/translated?language=English').get_data(as_text=True)
    assert 'Test Book' in english and 'Coming soon' in english
