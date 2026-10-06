from flask import Blueprint, session, request, redirect, url_for, render_template, flash, abort, current_app
from ..extensions import db
from ..models import Audiobook

bp = Blueprint('cart', __name__)

def cart_books():
    ids = [i for i in session.get('cart', []) if isinstance(i, int)][:30]
    books = db.session.scalars(db.select(Audiobook).where(Audiobook.id.in_(ids),
        Audiobook.state == 'published', Audiobook.saleable.is_(True))).all()
    if not (current_app.config['DEMO_MODE'] or current_app.config['SAMPLE_CATALOG']):
        books = [b for b in books if not b.is_demo]
    session['cart'] = [b.id for b in books]
    return books

@bp.get('/cart')
def index():
    books = cart_books()
    totals = {}
    for book in books:
        totals[book.currency] = totals.get(book.currency, 0) + book.price_minor
    return render_template('cart.html', books=books, totals=totals)

@bp.post('/cart/add/<int:book_id>')
def add(book_id):
    book = db.get_or_404(Audiobook, book_id)
    if book.state != 'published' or not book.saleable or (book.is_demo and not (current_app.config['DEMO_MODE'] or current_app.config['SAMPLE_CATALOG'])):
        abort(404)
    ids = session.get('cart', [])
    added = book_id not in ids
    if added and len(ids) >= 30:
        if request.accept_mimetypes.best == 'application/json':
            return {'error': 'Your cart is full. Remove a title before adding another.'}, 400
        flash('Your cart is full. Remove a title before adding another.', 'error')
        return redirect(url_for('cart.index'))
    if added:
        session['cart'] = ids + [book_id]
        if request.accept_mimetypes.best != 'application/json':
            flash(f'“{book.title}” added to your cart.', 'success')
    if request.accept_mimetypes.best == 'application/json':
        return {'count': len(session.get('cart', [])), 'added': added, 'title': book.title}
    return redirect(url_for('cart.index') if request.form.get('buy_now') else url_for('main.book', slug=book.slug))

@bp.post('/cart/remove/<int:book_id>')
def remove(book_id):
    session['cart'] = [i for i in session.get('cart', []) if i != book_id]
    return redirect(url_for('cart.index'))
