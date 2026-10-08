from app import create_app


def test_database_error_page_does_not_query_database_again(tmp_path):
    app = create_app({'TESTING':False, 'PRODUCTION':False, 'SECRET_KEY':'test-error-rendering-key',
        'SQLALCHEMY_DATABASE_URI':'sqlite://', 'RATELIMIT_ENABLED':False, 'DEMO_MODE':False, 'BUNNY_STORAGE_ZONE':'', 'BUNNY_STORAGE_ACCESS_KEY':''})
    # A new database with no migrations reproduces Render's missing-table failure.
    with app.test_client() as client:
        response = client.get('/')
        assert response.status_code == 500
        assert b'Something needs another take' in response.data
        assert client.get('/does-not-exist').status_code == 404


def test_render_gunicorn_initializes_database(monkeypatch):
    import runpy
    from unittest.mock import Mock
    config = runpy.run_path('gunicorn.conf.py')
    runner = Mock()
    monkeypatch.setattr(config['subprocess'], 'run', runner)
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.setenv('SAMPLE_CATALOG', 'false')
    config['on_starting'](Mock())
    assert runner.call_args_list[0].args[0][1:] == ['-m', 'flask', '--app', 'wsgi', 'db', 'upgrade']
    assert runner.call_args.kwargs['check'] is True
    runner.reset_mock()
    monkeypatch.delenv('RENDER')
    config['on_starting'](Mock())
    runner.assert_not_called()


def test_sample_catalog_seed_is_idempotent(app, client):
    from app.extensions import db
    from app.models import Audiobook
    from app.seed import TITLES
    app.config.update(PRODUCTION=True, SAMPLE_CATALOG=True)
    runner=app.test_cli_runner()
    assert runner.invoke(args=['seed-demo']).exit_code == 0
    assert runner.invoke(args=['seed-demo']).exit_code == 0
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Audiobook).where(Audiobook.is_demo.is_(True))) == len(TITLES)
    assert b'The Last Train to Lagos' in client.get('/books').data


def test_production_sample_cart_with_fresh_csrf(app, client):
    from app.extensions import db
    from app.models import Audiobook
    app.config.update(PRODUCTION=True, SAMPLE_CATALOG=True, WTF_CSRF_ENABLED=True)
    with app.app_context():
        book=db.session.get(Audiobook,app.config['TEST_BOOK_ID'])
        book.is_demo=True
        db.session.commit()
    path=f'/cart/add/{app.config["TEST_BOOK_ID"]}'
    rejected=client.post(path,headers={'Accept':'application/json'})
    assert rejected.status_code==400
    assert rejected.json['code']=='csrf_expired'
    token=client.get('/session/csrf')
    assert token.headers['Cache-Control']=='private, no-store'
    added=client.post(path,headers={'Accept':'application/json','X-CSRFToken':token.json['csrf_token']})
    assert added.status_code==200
    assert added.json['count']==1
    assert b'Test Book' in client.get('/cart').data


def test_https_cart_uses_same_origin_referrer_policy(app, client):
    app.config.update(WTF_CSRF_ENABLED=True)
    origin='https://example.com'
    token=client.get('/session/csrf',base_url=origin)
    assert token.headers['Referrer-Policy']=='same-origin'
    path=f'/cart/add/{app.config["TEST_BOOK_ID"]}'
    headers={'Accept':'application/json','X-CSRFToken':token.json['csrf_token']}
    assert client.post(path,base_url=origin,headers=headers).json['code']=='csrf_origin'
    headers['Referer']=origin+'/'
    response=client.post(path,base_url=origin,headers=headers)
    assert response.status_code==200
    assert response.json['count']==1
    headers['Referer']='https://untrusted.example/'
    assert client.post(path,base_url=origin,headers=headers).status_code==400
