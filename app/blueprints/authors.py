"""Author accounts: sign up for a subscription plan, sign in, and see your plan, trial and projects."""
from functools import wraps
from flask import Blueprint, render_template, request, session, redirect, url_for, flash, g
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from ..extensions import db, limiter
from ..models import AuthorAccount, AnalyticsEvent, now, uid
from ..services.access_service import normalize_email
from ..content.plans import PLANS, PLAN_KEYS, DEFAULT_PLAN, TRIAL_DAYS, LAUNCH

bp = Blueprint('authors', __name__, url_prefix='/authors')
# Equal password-check work for unknown addresses.
DUMMY_HASH = generate_password_hash('unused-author-password')
MIN_PASSWORD = 10
MAX_PASSWORD = 128


def current_author():
    """The signed-in author, or None. A password change or sign-out elsewhere ends old sessions."""
    if 'author' not in g:
        account = db.session.get(AuthorAccount, session['author_id']) if session.get('author_id') else None
        if account and session.get('author_version') != account.session_version:
            account = None
        if not account:
            session.pop('author_id', None)
            session.pop('author_version', None)
        g.author = account
    return g.author


def author_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_author():
            return redirect(url_for('authors.login', next=request.path))
        return fn(*args, **kwargs)
    return wrapped


def sign_in(account):
    session['author_id'] = account.id
    session['author_version'] = account.session_version
    session.permanent = True
    account.last_login_at = now()


def safe_next(default):
    target = request.values.get('next', '')
    return target if target.startswith('/authors/') and not target.startswith('//') else default


@bp.get('/')
def index():
    return redirect(url_for('authors.account' if current_author() else 'authors.signup'))


@bp.route('/signup', methods=['GET', 'POST'])
@limiter.limit('10 per hour', methods=['POST'])
def signup():
    if current_author():
        return redirect(url_for('authors.account'))
    chosen = request.values.get('plan', DEFAULT_PLAN)
    chosen = chosen if chosen in PLAN_KEYS else DEFAULT_PLAN
    errors = {}
    if request.method == 'POST':
        if request.form.get('website'):
            return redirect(url_for('authors.signup'))
        name = request.form.get('name', '').strip()[:150]
        password = request.form.get('password', '')
        try:
            email = normalize_email(request.form.get('email'))
        except ValueError:
            email = ''
        if not name:
            errors['name'] = 'Enter your name.'
        if not email:
            errors['email'] = 'Enter a valid email address.'
        if len(password) < MIN_PASSWORD:
            errors['password'] = f'Use at least {MIN_PASSWORD} characters.'
        elif len(password) > MAX_PASSWORD:
            errors['password'] = f'Use {MAX_PASSWORD} characters or fewer.'
        if not request.form.get('consent'):
            errors['consent'] = 'Please agree to the terms and privacy policy.'
        if not errors and db.session.scalar(db.select(AuthorAccount.id).where(AuthorAccount.email == email)):
            errors['email'] = 'An author account already uses this email. Log in instead.'
        if not errors:
            account = AuthorAccount(name=name, email=email, plan=chosen, pen_name=request.form.get('pen_name', '').strip()[:150],
                password_hash=generate_password_hash(password))
            db.session.add(account)
            db.session.add(AnalyticsEvent(kind='author_signup'))
            try:
                db.session.flush()
                sign_in(account)
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                errors['email'] = 'An author account already uses this email. Log in instead.'
            else:
                flash('sign_up', 'analytics')
                return redirect(url_for('authors.account', welcome=1))
    return render_template('authors/signup.html', plans=PLANS, chosen=PLAN_KEYS[chosen], errors=errors,
        trial_days=TRIAL_DAYS, launch=LAUNCH, min_password=MIN_PASSWORD), 400 if errors else 200


@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute', methods=['POST'])
def login():
    if current_author():
        return redirect(safe_next(url_for('authors.account')))
    if request.method == 'POST':
        try:
            email = normalize_email(request.form.get('email'))
        except ValueError:
            email = ''
        account = db.session.scalar(db.select(AuthorAccount).where(AuthorAccount.email == email)) if email else None
        password = request.form.get('password', '')
        valid = check_password_hash(account.password_hash if account else DUMMY_HASH, password[:1024])
        if account and valid and len(password) <= 1024:
            sign_in(account)
            db.session.commit()
            return redirect(safe_next(url_for('authors.account')))
        flash('Email or password is incorrect. Please try again.', 'error')
    return render_template('authors/login.html')


@bp.post('/logout')
def logout():
    session.pop('author_id', None)
    session.pop('author_version', None)
    flash('You have signed out of your author account.', 'success')
    return redirect(url_for('main.pricing'))


@bp.get('/account')
@author_required
def account():
    author = current_author()
    return render_template('authors/account.html', author=author, current=author.plan_details, plans=PLANS,
        trial_days=TRIAL_DAYS, launch=LAUNCH, welcome=request.args.get('welcome') == '1')


@bp.post('/account/plan')
@author_required
def change_plan():
    author = current_author()
    chosen = request.form.get('plan', '')
    if chosen not in PLAN_KEYS:
        flash('Choose one of the plans listed.', 'error')
    elif chosen != author.plan:
        author.plan = chosen
        db.session.commit()
        flash(f'You are now on the {PLAN_KEYS[chosen]["name"]} plan.', 'success')
    return redirect(url_for('authors.account') + '#plan')


@bp.post('/account/password')
@limiter.limit('10 per hour')
@author_required
def change_password():
    author = current_author()
    current, new = request.form.get('current_password', ''), request.form.get('new_password', '')
    if not check_password_hash(author.password_hash, current[:1024]):
        flash('Your current password is incorrect.', 'error')
    elif not MIN_PASSWORD <= len(new) <= MAX_PASSWORD:
        flash(f'Use a new password of {MIN_PASSWORD} to {MAX_PASSWORD} characters.', 'error')
    else:
        author.password_hash = generate_password_hash(new)
        author.session_version = uid()
        session['author_version'] = author.session_version
        db.session.commit()
        flash('Your password has been changed. Other devices have been signed out.', 'success')
    return redirect(url_for('authors.account') + '#security')


@bp.route('/forgot', methods=['GET', 'POST'])
@limiter.limit('5 per 15 minutes', methods=['POST'])
def forgot():
    from ..services import password_reset_service as resets
    if request.method == 'POST':
        try:
            email = normalize_email(request.form.get('email'))
        except ValueError:
            flash('Enter the email address you signed up with.', 'error')
            return render_template('authors/forgot.html'), 400
        response = redirect(url_for('authors.forgot', sent=1))
        return resets.after_response(response, resets.request_reset, 'author', email)
    return render_template('authors/forgot.html', sent=request.args.get('sent') == '1')


@bp.route('/reset/<token>', methods=['GET', 'POST'])
@limiter.limit('10 per 15 minutes', methods=['POST'])
def reset(token):
    from ..services import password_reset_service as resets
    _, account = resets.valid_reset('author', token)
    if not account:
        return render_template('authors/reset.html', expired=True), 410
    error = None
    if request.method == 'POST':
        password, confirm = request.form.get('password', ''), request.form.get('confirm', '')
        if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
            error = f'Use {MIN_PASSWORD} to {MAX_PASSWORD} characters.'
        elif password != confirm:
            error = 'The two passwords don’t match.'
        else:
            account = resets.complete('author', token, password)
            if not account:
                return render_template('authors/reset.html', expired=True), 410
            sign_in(account)
            db.session.commit()
            flash('Your password has been changed, and you’re signed in. Other devices have been signed out.', 'success')
            return resets.after_response(redirect(url_for('authors.account')), resets.notify_changed, 'author', account.id)
    return render_template('authors/reset.html', account=account, error=error, min_password=MIN_PASSWORD), 400 if error else 200
