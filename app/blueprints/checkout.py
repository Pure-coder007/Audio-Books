import stripe
from flask import Blueprint, request, current_app, render_template, redirect, url_for, flash, abort, session
from ..extensions import csrf, limiter, db
from ..models import Order
from ..services.access_service import normalize_email
from ..services.stripe_service import create_order, checkout_session, handle_event, PaymentMismatch
from .cart import cart_books

bp = Blueprint('checkout', __name__)

@bp.post('/checkout')
@limiter.limit('10 per hour')
def start():
    books = cart_books()
    try:
        email = normalize_email(request.form.get('email'))
        if not books:
            raise ValueError('Add an audiobook to your cart first.')
        if any(b.is_demo for b in books):
            flash('These are sample titles. Demo checkout never charges you or grants a purchase.', 'info')
            return render_template('checkout_demo.html', books=books)
        from ..services.storage_service import exists
        for book in books:
            assets = [chapter.media for chapter in book.chapters] if book.chapters else [book.asset('full')]
            if not assets or any(asset is None or not exists(asset.storage_key) for asset in assets):
                raise ValueError('The complete audio for a selected book is not ready. Please try again later or contact our team.')
        if not current_app.config['STRIPE_SECRET_KEY']:
            raise ValueError('Checkout is not available yet. Please try again later.')
        order = create_order(email, books)
        session['pending_order'] = order.id
        target = checkout_session(order)
        return redirect(target, code=303)
    except ValueError as error:
        flash(str(error), 'error')
    except stripe.StripeError:
        db.session.rollback()
        current_app.logger.warning('Stripe checkout unavailable.')
        flash('We could not reach the payment service. Please try again.', 'error')
    return redirect(url_for('cart.index'))

@bp.get('/checkout/success')
def success():
    order = db.session.get(Order, session.get('pending_order')) if session.get('pending_order') else None
    if order and order.stripe_session_id != request.args.get('session_id'):
        order = None
    if order and order.status == 'pending' and current_app.config['STRIPE_SECRET_KEY']:
        try:
            verified = stripe.checkout.Session.retrieve(order.stripe_session_id, api_key=current_app.config['STRIPE_SECRET_KEY'])
            if verified.get('payment_status') == 'paid':
                handle_event({'id': 'return-verified-' + verified['id'], 'type': 'checkout.session.completed', 'data': {'object': dict(verified)}})
        except (stripe.StripeError, PaymentMismatch):
            current_app.logger.warning('Checkout return could not verify payment; awaiting webhook.')
    if order and order.status == 'paid':
        session['cart'] = []
        session['listener_email'] = order.email
        session.permanent = True
    return render_template('checkout_success.html', order=order)

@bp.post('/checkout/webhook')
@csrf.exempt
@limiter.exempt
def webhook():
    secret = current_app.config['STRIPE_WEBHOOK_SECRET']
    if not secret:
        abort(503)
    try:
        event = stripe.Webhook.construct_event(request.get_data(), request.headers.get('Stripe-Signature', ''), secret)
    except (ValueError, stripe.SignatureVerificationError):
        abort(400)
    try:
        result = handle_event(event)
    except PaymentMismatch:
        current_app.logger.error('Rejected a payment whose session or totals did not match its order.')
        abort(400)
    return {'received': True, 'result': result}
