import os
import secrets
from pathlib import Path
from datetime import timedelta
from flask import Flask, render_template, session, request, g
from .config import Config
from .extensions import db, migrate, csrf, limiter

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
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    from .blueprints import main, cart, checkout, library, admin, auth
    for module in [main, cart, checkout, library, admin, auth]:
        app.register_blueprint(module.bp)
    from .cli import register_commands
    register_commands(app)
    @app.before_request
    def csp_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)
    @app.context_processor
    def shared():
        from .models import Category
        from .genre_themes import genre_theme
        return {'genre_theme': genre_theme, 'genres': db.session.scalars(db.select(Category).order_by(Category.position, Category.name)).all(),
            'cart_count': len(session.get('cart', [])), 'demo_mode': app.config['DEMO_MODE']}
    @app.template_filter('reject_page')
    def reject_page(args):
        return {key: value for key, value in args.items() if key != 'page'}
    @app.template_filter('with_view_args')
    def with_view_args(args):
        return {**args, **(request.view_args or {})}
    @app.template_filter('money')
    def money(value, currency='ngn'):
        symbols = {'ngn': '₦', 'usd': '$', 'gbp': '£', 'eur': '€'}
        return symbols.get(currency, currency.upper() + ' ') + f'{value / 100:,.2f}'.removesuffix('.00')
    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
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
            db.session.rollback()
            return render_template('error.html', code=code), code
        app.register_error_handler(code, handler)
    return app
