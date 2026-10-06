from app import create_app


def test_database_error_page_does_not_query_database_again(tmp_path):
    app = create_app({'TESTING':False, 'PRODUCTION':False, 'SECRET_KEY':'test-error-rendering-key',
        'SQLALCHEMY_DATABASE_URI':'sqlite://', 'RATELIMIT_ENABLED':False, 'DEMO_MODE':False})
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
    assert runner.call_args.args[0][1:] == ['-m', 'flask', '--app', 'wsgi', 'db', 'upgrade']
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
