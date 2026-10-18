import json
from app.extensions import db
from app.models import AuditLog


def sign_in(client):
    response = client.post('/admin/login', data={'email': 'owner@example.com', 'password': 'test-password-long'})
    assert response.status_code == 302


def tour_data(client, path='/admin/'):
    page = client.get(path).data.decode()
    assert 'js/admin-tour.js' in page and 'data-tour-start' in page
    return json.loads(page.split('id="tour-data"', 1)[1].split('>', 1)[1].split('</script>', 1)[0])


def test_tour_opens_automatically_for_the_first_five_sign_ins(client):
    for number in range(1, 6):
        sign_in(client)
        data = tour_data(client)
        assert data['auto'] and data['sign_in'] == number and data['page'] == 'dashboard'
        client.post('/admin/logout')
    sign_in(client)
    data = tour_data(client)
    assert not data['auto'] and data['steps'], 'the tour can still be replayed after five sign-ins'


def test_each_page_has_its_own_tour_and_seen_pages_stay_quiet(client):
    sign_in(client)
    assert client.post('/admin/tour', json={'action': 'seen', 'page': 'dashboard'}).status_code == 200
    assert not tour_data(client)['auto']
    books = tour_data(client, '/admin/books')
    assert books['auto'] and books['page'] == 'books'
    editor = tour_data(client, '/admin/books/new')
    assert editor['page'] == 'editor' and any(step['target'] == 'editor-featured' for step in editor['steps'])
    assert 'data-tour="editor-featured"' in client.get('/admin/books/new').data.decode()


def test_skip_quiets_this_sign_in_only(client):
    sign_in(client)
    client.post('/admin/tour', json={'action': 'skip', 'page': 'dashboard'})
    assert not tour_data(client, '/admin/books')['auto']
    client.post('/admin/logout')
    sign_in(client)
    assert tour_data(client)['auto']


def test_dont_show_again_turns_the_tour_off_for_good(client, app):
    sign_in(client)
    client.post('/admin/tour', json={'action': 'never', 'page': 'dashboard'})
    assert not tour_data(client)['auto']
    client.post('/admin/logout')
    sign_in(client)
    assert not tour_data(client)['auto']
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(AuditLog).where(AuditLog.action == 'tour.dismissed')) == 1


def test_tour_endpoint_validates_input_and_requires_staff(client):
    assert client.post('/admin/tour', json={'action': 'seen', 'page': 'dashboard'}).status_code == 302
    sign_in(client)
    assert client.post('/admin/tour', json={'action': 'dance', 'page': 'dashboard'}).status_code == 400
    assert client.post('/admin/tour', json={'action': 'seen', 'page': 'nowhere'}).status_code == 400
