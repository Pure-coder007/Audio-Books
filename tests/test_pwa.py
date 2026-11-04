from pathlib import Path
from PIL import Image
from app.extensions import db
from app.models import AnalyticsEvent

STATIC = Path(__file__).resolve().parent.parent / 'app' / 'static'


def static_file(url):
    # Static URLs carry a ?v= content hash for long browser caching.
    assert url.startswith('/static/')
    return STATIC / url.removeprefix('/static/').split('?')[0]


def test_manifest_makes_the_site_installable(client):
    response = client.get('/manifest.webmanifest')
    assert response.status_code == 200
    assert response.mimetype == 'application/manifest+json'
    manifest = response.get_json(force=True)
    assert manifest['name'] == 'MyAudioShelf' and manifest['display'] == 'standalone'
    assert manifest['start_url'] == '/' and manifest['scope'] == '/'
    purposes = {(icon['sizes'], icon['purpose']) for icon in manifest['icons']}
    assert {('192x192', 'any'), ('512x512', 'any'), ('512x512', 'maskable')} <= purposes
    # Every icon and screenshot exists at the size the manifest declares.
    for image in manifest['icons'] + manifest['screenshots'] + [icon for shortcut in manifest['shortcuts'] for icon in shortcut['icons']]:
        width, height = map(int, image['sizes'].split('x'))
        assert Image.open(static_file(image['src'])).size == (width, height)
    # Chrome's richer install sheet needs both a wide and a narrow screenshot.
    assert {shot['form_factor'] for shot in manifest['screenshots']} == {'wide', 'narrow'}


def test_install_icons_are_opaque_where_platforms_require_it():
    for name in ['apple-touch-icon.png', 'app-maskable-512.png']:
        image = Image.open(STATIC / 'icons' / name).convert('RGBA')
        assert image.getchannel('A').getextrema() == (255, 255)


def test_service_worker_is_served_from_the_root_without_caching(client):
    response = client.get('/sw.js')
    assert response.status_code == 200
    assert response.mimetype == 'text/javascript'
    assert response.headers['Cache-Control'] == 'no-cache'
    source = response.get_data(as_text=True)
    # Purchased audio and downloads must never pass through the worker's cache.
    for path in ['/media/private/', '/library/download/', '/admin', '/checkout']:
        assert f"'{path}'" in source


def test_pages_link_the_manifest_and_install_prompt(client):
    html = client.get('/').get_data(as_text=True)
    assert '<link rel="manifest" href="/manifest.webmanifest">' in html
    assert 'icons/apple-touch-icon.png' in html
    assert 'js/install.js' in html
    assert 'data-install-open hidden' in html


def test_app_installs_are_counted_on_the_dashboard(app, client, admin_client):
    assert client.post('/engagement', json={'kind': 'app_install'}).status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(AnalyticsEvent).where(AnalyticsEvent.kind == 'app_install')) == 1
    assert b'App installs' in admin_client.get('/admin/').data
