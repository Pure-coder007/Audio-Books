import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def database_url(value):
    # Neon supplies a PostgreSQL URL; use the psycopg 3 driver installed here.
    for prefix in ('postgres://', 'postgresql://'):
        if value.startswith(prefix):
            return 'postgresql+psycopg://' + value[len(prefix):]
    return value

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = database_url(os.environ.get('DATABASE_URL', 'sqlite:///myaudioshelf.db'))
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BASE_URL = os.environ.get('BASE_URL', 'http://127.0.0.1:5000').rstrip('/')
    PRODUCTION = os.environ.get('APP_ENV') == 'production'
    SAMPLE_CATALOG = os.environ.get('SAMPLE_CATALOG', os.environ.get('RENDER', 'false')).lower() == 'true'
    DEMO_MODE = os.environ.get('DEMO_MODE', 'false').lower() == 'true' and not PRODUCTION
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = PRODUCTION
    MAX_CONTENT_LENGTH = 512 * 1024 * 1024
    STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
    MAIL_HOST = os.environ.get('MAIL_HOST', '')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_FROM = os.environ.get('MAIL_FROM', 'MyAudioShelf <hello@example.com>')
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
    MEDIA_TOKEN_TTL = 3600
    MAGIC_LINK_TTL = 900

    BUNNY_STORAGE_ZONE = os.environ.get('BUNNY_STORAGE_ZONE', '').strip()
    BUNNY_STORAGE_ACCESS_KEY = os.environ.get('BUNNY_STORAGE_ACCESS_KEY', '').strip()
    BUNNY_STORAGE_ENDPOINT = (os.environ.get('BUNNY_STORAGE_ENDPOINT') or 'https://storage.bunnycdn.com').rstrip('/')
