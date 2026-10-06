import stripe
from flask import current_app
from sqlalchemy.exc import IntegrityError
from ..extensions import db
from ..models import Order, OrderItem, PurchaseEntitlement, StripeEvent, PaymentRefund, now
from .email_service import queue_access_email

class PaymentMismatch(ValueError):
    pass

def create_order(email, books):
    currencies = {b.currency for b in books}
    if len(currencies) != 1:
        raise ValueError('Checkout requires all books to use the same currency.')
    if any(b.is_demo or b.state != 'published' or not b.saleable or b.price_minor <= 0 for b in books):
        raise ValueError('A selected book is not available for purchase.')
    order = Order(email=email, total_minor=sum(b.price_minor for b in books), currency=currencies.pop())
    db.session.add(order)
    for book in books:
        order.items.append(OrderItem(book_id=book.id, title=book.title, price_minor=book.price_minor))
    db.session.commit()
    return order

def checkout_session(order):
    result = stripe.checkout.Session.create(api_key=current_app.config['STRIPE_SECRET_KEY'],
        mode='payment', customer_email=order.email,
        client_reference_id=order.id, metadata={'order_id': order.id},
        line_items=[{'quantity': 1, 'price_data': {'currency': order.currency,
            'unit_amount': item.price_minor, 'product_data': {'name': item.title}}} for item in order.items],
        success_url=current_app.config['BASE_URL'] + '/checkout/success?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=current_app.config['BASE_URL'] + '/cart',
        idempotency_key='checkout-' + order.id)
    order.stripe_session_id = result.id
    db.session.commit()
    return result.url

def handle_event(event):
    """Entire receipt, payment state, entitlements and email queue commit atomically."""
    if db.session.get(StripeEvent, event['id']):
        return 'duplicate'
    kind = event['type']
    obj = event['data']['object']
    accepted = {'checkout.session.completed', 'checkout.session.async_payment_succeeded',
        'checkout.session.async_payment_failed', 'checkout.session.expired', 'charge.refunded'}
    if kind not in accepted:
        return 'ignored'
    try:
        db.session.add(StripeEvent(id=event['id'], event_type=kind))
        db.session.flush()
        if kind == 'charge.refunded':
            payment_id = obj.get('payment_intent')
            if obj.get('refunded') and payment_id and not db.session.get(PaymentRefund, payment_id):
                db.session.add(PaymentRefund(payment_intent_id=payment_id, stripe_event_id=event['id']))
            order = db.session.scalar(db.select(Order).where(Order.stripe_payment_id == obj.get('payment_intent')).with_for_update())
            # Partial refunds require manual entitlement review; full refunds revoke access.
            if order and obj.get('refunded'):
                order.status = 'refunded'
                entitlements = db.session.scalars(db.select(PurchaseEntitlement).where(PurchaseEntitlement.order_id == order.id)).all()
                for entitlement in entitlements:
                    previous = db.session.scalar(db.select(Order).join(OrderItem).where(
                        Order.email == entitlement.email, Order.status == 'paid', Order.id != order.id,
                        OrderItem.book_id == entitlement.book_id).order_by(Order.paid_at.desc()))
                    if previous:
                        entitlement.order_id = previous.id
                    else:
                        entitlement.active = False
        else:
            order_id = obj.get('metadata', {}).get('order_id')
            order = db.session.scalar(db.select(Order).where(Order.id == order_id).with_for_update()) if order_id else None
            if not order:
                db.session.commit()
                return 'unrelated'
            if order.stripe_session_id != obj.get('id'):
                raise PaymentMismatch('Checkout session does not match the order.')
            if kind in {'checkout.session.completed', 'checkout.session.async_payment_succeeded'}:
                if obj.get('payment_status') != 'paid':
                    db.session.commit()
                    return 'awaiting-payment'
                if obj.get('amount_total') != order.total_minor or obj.get('currency') != order.currency:
                    raise PaymentMismatch('Payment amount or currency does not match the order.')
                if order.status != 'paid' and order.status != 'refunded':
                    order.stripe_payment_id = obj.get('payment_intent')
                    if order.stripe_payment_id and db.session.get(PaymentRefund, order.stripe_payment_id):
                        order.status = 'refunded'
                        db.session.commit()
                        return 'already-refunded'
                    order.status = 'paid'
                    order.paid_at = now()
                    for item in order.items:
                        entitlement = db.session.scalar(db.select(PurchaseEntitlement).where(
                            PurchaseEntitlement.email == order.email, PurchaseEntitlement.book_id == item.book_id))
                        if entitlement:
                            entitlement.active = True
                            entitlement.order_id = order.id
                        else:
                            db.session.add(PurchaseEntitlement(email=order.email, book_id=item.book_id, order_id=order.id))
                    queue_access_email(order.email)
            elif order.status == 'pending':
                order.status = 'failed' if kind.endswith('failed') else 'expired'
        db.session.commit()
        return 'processed'
    except IntegrityError:
        db.session.rollback()
        if db.session.get(StripeEvent, event['id']):
            return 'duplicate'
        raise
    except Exception:
        db.session.rollback()
        raise
