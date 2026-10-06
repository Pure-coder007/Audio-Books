import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from app.extensions import db
from app.models import Audiobook, Order, OrderItem, PurchaseEntitlement, StripeEvent, EmailDelivery
from app.services.stripe_service import create_order, handle_event, PaymentMismatch

def event_for(order, event_id='evt_1', **changes):
    obj={'id':order.stripe_session_id,'metadata':{'order_id':order.id},'payment_status':'paid',
        'amount_total':order.total_minor,'currency':order.currency,'payment_intent':'pi_fixture'}
    obj.update(changes)
    return {'id':event_id,'type':'checkout.session.completed','data':{'object':obj}}

def signed_post(client, event, secret='whsec_fixture'):
    payload=json.dumps(event).encode();timestamp=str(int(time.time()))
    signature=hmac.new(secret.encode(),timestamp.encode()+b'.'+payload,hashlib.sha256).hexdigest()
    return client.post('/checkout/webhook',data=payload,content_type='application/json',headers={'Stripe-Signature':f't={timestamp},v1={signature}'})

def pending(app):
    book=db.session.get(Audiobook,app.config['TEST_BOOK_ID'])
    order=create_order('buyer@example.com',[book]);order.stripe_session_id='cs_fixture';db.session.commit()
    return order

def test_cart_deduplicates_and_ignores_client_prices(client,app):
    book_id=app.config['TEST_BOOK_ID']
    client.post(f'/cart/add/{book_id}',data={'price_minor':1})
    client.post(f'/cart/add/{book_id}')
    with client.session_transaction() as session: assert session['cart']==[book_id]
    assert '₦4,500'.encode() in client.get('/cart').data

def test_checkout_uses_authoritative_snapshot(client,app):
    client.post(f'/cart/add/{app.config["TEST_BOOK_ID"]}')
    with patch('stripe.checkout.Session.create',return_value=SimpleNamespace(id='cs_fixture',url='https://checkout.stripe.com/test')) as create:
        response=client.post('/checkout',data={'email':'BUYER@example.com','total_minor':1})
        assert response.status_code==303
        data=create.call_args.kwargs
        assert data['line_items'][0]['price_data']['unit_amount']==450000
        assert data['line_items'][0]['quantity']==1
        assert data['customer_email']=='buyer@example.com'
    with app.app_context():
        order=db.session.scalar(db.select(Order));assert order.total_minor==450000
        assert order.items[0].price_minor==450000
        assert order.status=='pending'
        assert db.session.scalar(db.select(db.func.count()).select_from(PurchaseEntitlement))==0

def test_success_url_never_unlocks_audio(client,app):
    with app.app_context(): order=pending(app);order_id=order.id
    with client.session_transaction() as session: session['pending_order']=order_id
    assert client.get('/checkout/success?session_id=cs_fixture').status_code==200
    with app.app_context(): assert db.session.scalar(db.select(db.func.count()).select_from(PurchaseEntitlement))==0
    assert client.get('/media/private/'+'a'*32).status_code==403

def test_webhook_verifies_signature(client,app):
    assert client.post('/checkout/webhook',data='{}').status_code==400
    with app.app_context(): event=event_for(pending(app))
    assert signed_post(client,event,secret='incorrect').status_code==400
    assert signed_post(client,event).status_code==200
    assert signed_post(client,event).json['result']=='duplicate'
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(PurchaseEntitlement))==1
        assert db.session.scalar(db.select(db.func.count()).select_from(EmailDelivery))==1

@pytest.mark.parametrize('changes',[{'amount_total':1},{'currency':'usd'},{'id':'cs_wrong'}])
def test_mismatched_payments_rollback(app,changes):
    with app.app_context():
        order=pending(app);event=event_for(order,**changes)
        with pytest.raises(PaymentMismatch):handle_event(event)
        assert db.session.get(StripeEvent,event['id']) is None
        assert db.session.get(Order,order.id).status=='pending'
        assert db.session.scalar(db.select(db.func.count()).select_from(PurchaseEntitlement))==0

def test_delayed_payment_waits_for_paid_event(app):
    with app.app_context():
        order=pending(app)
        assert handle_event(event_for(order,payment_status='unpaid'))=='awaiting-payment'
        assert order.status=='pending'
        event=event_for(order,event_id='evt_async');event['type']='checkout.session.async_payment_succeeded'
        assert handle_event(event)=='processed'
        assert order.status=='paid'

def test_full_refund_revokes_access(app):
    with app.app_context():
        order=pending(app);handle_event(event_for(order))
        event={'id':'evt_refund','type':'charge.refunded','data':{'object':{'payment_intent':'pi_fixture','refunded':True}}}
        assert handle_event(event)=='processed'
        assert order.status=='refunded'
        assert not db.session.scalar(db.select(PurchaseEntitlement)).active
        later=event_for(order,event_id='evt_later');handle_event(later)
        assert not db.session.scalar(db.select(PurchaseEntitlement)).active

def test_second_payment_event_does_not_duplicate_email(app):
    with app.app_context():
        order=pending(app);handle_event(event_for(order));handle_event(event_for(order,event_id='evt_2'))
        assert db.session.scalar(db.select(db.func.count()).select_from(EmailDelivery))==1

def test_demo_books_cannot_create_real_order(app):
    with app.app_context():
        book=db.session.get(Audiobook,app.config['TEST_BOOK_ID']);book.is_demo=True
        with pytest.raises(ValueError):create_order('buyer@example.com',[book])

def test_mixed_currencies_rejected(app):
    with app.app_context():
        book=db.session.get(Audiobook,app.config['TEST_BOOK_ID'])
        other=Audiobook(title='Other',slug='other',author=book.author,price_minor=1000,currency='usd',state='published')
        db.session.add(other);db.session.commit()
        with pytest.raises(ValueError):create_order('buyer@example.com',[book,other])

def test_unpublished_books_not_saleable(client,app):
    with app.app_context():
        book=db.session.get(Audiobook,app.config['TEST_BOOK_ID']);book.state='draft';db.session.commit()
    assert client.post(f'/cart/add/{app.config["TEST_BOOK_ID"]}').status_code==404
    assert client.get('/books/test-book').status_code==404

def test_changed_book_price_does_not_change_order(app):
    with app.app_context():
        order=pending(app);book=db.session.get(Audiobook,app.config['TEST_BOOK_ID'])
        book.price_minor=500000;db.session.commit()
        assert order.total_minor==450000 and order.items[0].price_minor==450000

def test_refund_before_checkout_event_does_not_unlock(app):
    with app.app_context():
        order=pending(app)
        refund={'id':'evt_early_refund','type':'charge.refunded','data':{'object':{'payment_intent':'pi_fixture','refunded':True}}}
        handle_event(refund)
        assert handle_event(event_for(order))=='already-refunded'
        assert order.status=='refunded'
        assert db.session.scalar(db.select(db.func.count()).select_from(PurchaseEntitlement))==0

def test_refund_preserves_another_paid_purchase(app):
    with app.app_context():
        first=pending(app);handle_event(event_for(first))
        book=db.session.get(Audiobook,app.config['TEST_BOOK_ID'])
        second=create_order('buyer@example.com',[book]);second.stripe_session_id='cs_second';db.session.commit()
        handle_event(event_for(second,event_id='evt_second_purchase',payment_intent='pi_second'))
        entitlement=db.session.scalar(db.select(PurchaseEntitlement));assert entitlement.order_id==second.id
        handle_event({'id':'evt_second_refund','type':'charge.refunded','data':{'object':{'payment_intent':'pi_second','refunded':True}}})
        assert entitlement.active and entitlement.order_id==first.id

def test_ajax_cart_add_stays_on_shelf_and_deduplicates(client,app):
    path=f'/cart/add/{app.config["TEST_BOOK_ID"]}'
    first=client.post(path,headers={'Accept':'application/json'})
    assert first.status_code==200 and first.json['count']==1 and first.json['added'] is True
    second=client.post(path,headers={'Accept':'application/json'})
    assert second.status_code==200 and second.json['count']==1 and second.json['added'] is False
