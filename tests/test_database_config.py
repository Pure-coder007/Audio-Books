from app.config import database_url


def test_postgresql_url_uses_psycopg_and_retains_tls():
    for scheme in ['postgres','postgresql']:
        assert database_url(f'{scheme}://example/db?sslmode=require&channel_binding=require') == 'postgresql+psycopg://example/db?sslmode=require&channel_binding=require'
    assert database_url('sqlite:///local.db')=='sqlite:///local.db'
    assert database_url('postgresql+psycopg://example/db')=='postgresql+psycopg://example/db'
