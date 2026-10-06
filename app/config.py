import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///myaudioshelf.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BASE_URL = os.environ.get('BASE_URL', 'http://127.0.0.1:5000').rstrip('/')
    PRODUCTION = os.environ.get('APP_ENV') == 'production'
    DEMO_MODE = os.environ.get('DEMO_MODE', 'false').lower() == 'true' and not PRODUCTION
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = PRODUCTION
    MAX_CONTENT_LENGTH = 512 * 1024 * 1024
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
