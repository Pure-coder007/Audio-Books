import os
import secrets
from collections.abc import Sequence
from pathlib import Path
from datetime import timedelta
from flask import Flask, render_template, session, request, g
from flask_wtf.csrf import CSRFError, generate_csrf
from .config import Config
from .extensions import db, migrate, csrf, limiter

class Deferred(Sequence):
    """A list that runs its query only when a template first reads it."""
    def __init__(self, load):
        self._load, self._items = load, None
    def _all(self):
        if self._items is None:
            self._items = self._load()
        return self._items
    def __getitem__(self, index):
        return self._all()[index]
    def __len__(self):
        return len(self._all())

def create_app(test_config=None):
    from .services.logging_service import configure_token_redaction
    configure_token_redaction()
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.setdefault('MEDIA_ROOT', str(Path(app.instance_path) / 'media'))
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
    if not app.config.get('SECRET_KEY'):
        if app.config['PRODUCTION']:
            raise RuntimeError('SECRET_KEY is required in production.')
        path = Path(app.instance_path) / '.dev-secret'
        if not path.exists():
            path.write_text(secrets.token_hex(32))
            path.chmod(0o600)
        app.config['SECRET_KEY'] = path.read_text().strip()
    if app.config['PRODUCTION']:
        if len(app.config['SECRET_KEY']) < 32:
            raise RuntimeError('Production SECRET_KEY must have at least 32 characters.')
        if not app.config['BASE_URL'].startswith('https://'):
            raise RuntimeError('Production BASE_URL must use HTTPS.')
        app.config['SESSION_COOKIE_SECURE'] = True
        app.config['DEMO_MODE'] = False
    from .services.storage_service import validate_config, StorageError
    validate_config(app.config)
    @app.errorhandler(StorageError)
    def storage_error(error):
        app.logger.warning('Private media storage request failed.')
        g.rendering_error = True
        db.session.rollback()
        return render_template('error.html', code=503), 503
    db.init_app(app)
    # Establish the intended schema explicitly when using transaction poolers.
    with app.app_context():
        if db.engine.dialect.name == 'postgresql':
            from sqlalchemy import event
            @event.listens_for(db.engine, 'connect')
            def public_schema(connection, record):
                with connection.cursor() as cursor:
                    cursor.execute('SET search_path TO public')
                connection.commit()
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    from .blueprints import main, cart, checkout, library, admin, auth
    for module in [main, cart, checkout, library, admin, auth]:
        app.register_blueprint(module.bp)
    from .cli import register_commands
    register_commands(app)
    @app.get('/session/csrf')
    def session_csrf():
        return {'csrf_token': generate_csrf()}

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        if request.accept_mimetypes.best == 'application/json':
            token_error = 'referrer' not in error.description.lower()
            return {'error': 'Your session has expired. Refresh the page and try again.' if token_error else 'Could not verify this request. Reload the page and try again.', 'code': 'csrf_expired' if token_error else 'csrf_origin'}, 400
        g.rendering_error = True
        return render_template('error.html', code=400), 400

    @app.before_request
    def csp_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)
    @app.before_request
    def migrated_references():
        from .services.identity_service import resolve_id
        from flask import abort
        tables = {'book_id': 'audiobook', 'chapter_id': 'chapter',
                  'entitlement_id': 'purchase_entitlement', 'user_id': 'admin_user',
                  'enquiry_id': 'production_enquiry', 'order_id': 'order', 'media_id': 'media_asset'}
        for field, value in (request.view_args or {}).items():
            if field in tables:
                resolved = resolve_id(tables[field], value)
                if not resolved:
                    abort(404)
                request.view_args[field] = resolved
        if session.get('admin_id') is not None:
            resolved = resolve_id('admin_user', session['admin_id'])
            if resolved:
                session['admin_id'] = resolved
            else:
                session.pop('admin_id', None)
        if session.get('cart'):
            session['cart'] = list(dict.fromkeys(value for old in session['cart'][:30]
                if (value := resolve_id('audiobook', old))))

    @app.context_processor
    def shared():
        from .models import Category
        from .genre_themes import genre_theme
        from .content.company import SOCIAL_LINKS
        from .content.legal import COMPANY
        return {'genre_theme': genre_theme, 'social_links': SOCIAL_LINKS, 'company': COMPANY, 'genres': [] if getattr(g, 'rendering_error', False) else Deferred(lambda: db.session.scalars(db.select(Category).order_by(Category.position, Category.name)).all()),
            'cart_count': len(session.get('cart', [])), 'demo_mode': app.config['DEMO_MODE']}
    @app.template_filter('reject_page')
    def reject_page(args):
        return {key: value for key, value in args.items() if key != 'page'}
    @app.template_filter('with_view_args')
    def with_view_args(args):
        return {**args, **(request.view_args or {})}
    @app.template_filter('money')
    def money(value, currency='gbp'):
        symbols = {'ngn': '₦', 'usd': '$', 'gbp': '£', 'eur': '€'}
        return symbols.get(currency, currency.upper() + ' ') + f'{value / 100:,.2f}'.removesuffix('.00')
    @app.after_request
    def headers(response):
        if request.method == 'GET' and response.status_code == 200 and response.mimetype == 'text/html' and request.blueprint == 'main':
            from .services.analytics_service import record_after_response
            record_after_response(response, kind=('page_view:' + request.path)[:100])
        # Every rendered page contains session-bound CSRF tokens.
        if response.mimetype == 'text/html' or request.path == '/session/csrf':
            response.headers['Cache-Control'] = 'private, no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self'; script-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self' https://checkout.stripe.com"
        if getattr(g, 'csp_nonce', None):
            response.headers['Content-Security-Policy'] = response.headers['Content-Security-Policy'].replace("script-src 'self'", "script-src 'self' 'nonce-" + g.csp_nonce + "'")
        if request.path.startswith(('/admin', '/library', '/checkout', '/cart', '/media/private', '/login', '/register')):
            response.headers['Cache-Control'] = 'private, no-store'
            response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        if app.config['PRODUCTION']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response
    for code in [400, 403, 404, 413, 429, 500, 503]:
        def handler(error, code=code):
            g.rendering_error = True
            db.session.rollback()
            return render_template('error.html', code=code), code
        app.register_error_handler(code, handler)
    return app
