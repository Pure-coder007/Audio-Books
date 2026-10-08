import io
from zipfile import ZipFile
from app.extensions import db
from app.models import Audiobook, Chapter, MediaAsset, Order, PurchaseEntitlement


def signed_in(client):
    with client.session_transaction() as session:session['listener_email']='buyer@example.com'


def test_download_requires_paid_purchase(client,app,paid_order):
    path=f'/library/download/{app.config["TEST_BOOK_ID"]}'
    assert client.get(path).status_code==403
    signed_in(client)
    response=client.get(path)
    assert response.status_code==200
    assert 'attachment' in response.headers['Content-Disposition']
    assert response.headers['Cache-Control']=='private, no-store'
    with app.app_context():
        db.session.get(Order,paid_order).status='pending';db.session.commit()
    assert client.get(path).status_code==403


def test_chapter_zip_contains_every_track_in_order(client,app,paid_order):
    with app.app_context():
        book=db.session.get(Audiobook,app.config['TEST_BOOK_ID'])
        for position,title in [(2,'Second'),(1,'First')]:
            asset=MediaAsset(book=book,kind='chapter',storage_key='private.wav',mime_type='audio/wav',duration_seconds=2)
            db.session.add(Chapter(book=book,title=title,position=position,media=asset))
        db.session.commit()
    signed_in(client)
    response=client.get(f'/library/download/{app.config["TEST_BOOK_ID"]}')
    assert response.status_code==200
    with ZipFile(io.BytesIO(response.data)) as package:
        assert package.namelist()==['001 - First.wav','002 - Second.wav','Contents.txt']
        assert package.read('001 - First.wav').startswith(b'RIFF')
    with app.app_context():
        item=db.session.scalar(db.select(PurchaseEntitlement));item.active=False;db.session.commit()
    assert client.get(f'/library/download/{app.config["TEST_BOOK_ID"]}').status_code==403


def test_missing_chapter_does_not_produce_incomplete_zip(client,app,paid_order):
    with app.app_context():
        book=db.session.get(Audiobook,app.config['TEST_BOOK_ID'])
        asset=MediaAsset(book=book,kind='chapter',storage_key='missing.mp3',mime_type='audio/mpeg')
        db.session.add(Chapter(book=book,title='Missing',position=1,media=asset));db.session.commit()
    signed_in(client)
    response=client.get(f'/library/download/{app.config["TEST_BOOK_ID"]}')
    assert response.status_code==302
    assert response.location=='/library'


def test_checkout_return_verifies_stripe_before_unlocking(client,app,paid_order,monkeypatch):
    from app.models import Order
    from app.blueprints.checkout import stripe
    with app.app_context():
        order=db.session.get(Order,paid_order)
        order.status='pending'
        db.session.scalar(db.select(PurchaseEntitlement)).active=False
        db.session.commit()
        amount,currency=order.total_minor,order.currency
    with client.session_transaction() as session:session['pending_order']=paid_order
    monkeypatch.setattr(stripe.checkout.Session,'retrieve',lambda *args,**kwargs:{'id':'cs_paid','payment_status':'paid','amount_total':amount,'currency':currency,'payment_intent':'pi_download','metadata':{'order_id':paid_order}})
    response=client.get('/checkout/success?session_id=cs_paid')
    assert response.status_code==200
    assert b'Download Test Book' in response.data
    with client.session_transaction() as session:assert session['listener_email']=='buyer@example.com'
    assert client.get(f'/library/download/{app.config["TEST_BOOK_ID"]}').status_code==200


def test_success_query_cannot_unlock_another_order(client,app,paid_order,monkeypatch):
    from app.blueprints.checkout import stripe
    def unexpected(*args,**kwargs):raise AssertionError('Should not retrieve unrelated sessions')
    monkeypatch.setattr(stripe.checkout.Session,'retrieve',unexpected)
    with client.session_transaction() as session:session['pending_order']=paid_order
    client.get('/checkout/success?session_id=unrelated')
    with client.session_transaction() as session:assert 'listener_email' not in session


def test_checkout_blocks_missing_full_recordings(client,app,monkeypatch):
    from pathlib import Path
    from app.blueprints.checkout import stripe
    def unexpected(*args,**kwargs):raise AssertionError('Must not create a payment for unavailable recordings')
    monkeypatch.setattr(stripe.checkout.Session,'create',unexpected)
    (Path(app.config['MEDIA_ROOT'])/'private.wav').unlink()
    client.post(f'/cart/add/{app.config["TEST_BOOK_ID"]}')
    response=client.post('/checkout',data={'email':'buyer@example.com'},follow_redirects=True)
    assert b'complete audio' in response.data
