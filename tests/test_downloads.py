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
