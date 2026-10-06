from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from ..extensions import db, limiter
from ..models import Customer
from ..services.access_service import normalize_email

bp = Blueprint('auth', __name__)
# Equal password-check work for unknown addresses.
DUMMY_HASH = generate_password_hash('unused-customer-password')

@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute', methods=['POST'])
def login():
    if session.get('listener_email'):
        return redirect(url_for('library.index'))
    if request.method == 'POST':
        try:
            email = normalize_email(request.form.get('email'))
        except ValueError:
            email = ''
        customer = db.session.scalar(db.select(Customer).where(Customer.email == email))
        password = request.form.get('password', '')
        valid = check_password_hash(customer.password_hash if customer else DUMMY_HASH, password[:1024])
        if customer and valid and len(password) <= 1024:
            cart = session.get('cart', [])
            session.clear()
            session['cart'] = cart
            session['listener_email'] = customer.email
            session.permanent = True
            return redirect(url_for('library.index'))
        flash('Email or password is incorrect. Please try again.', 'error')
    return render_template('login.html')

