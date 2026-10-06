from datetime import timedelta
from urllib.parse import urlparse
from unittest.mock import patch
import pytest
from app.extensions import db
from app.models import MagicLink, PurchaseEntitlement, ListeningProgress, now
from app.services.access_service import issue_magic_link, consume_magic_link, media_token

def sign_in(client):
    with client.session_transaction() as session: session['listener_email']='buyer@example.com'

def test_magic_link_single_use_and_scanner_safe(client,app,paid_order):
    with app.app_context():url=issue_magic_link('buyer@example.com');db.session.commit()
    path=urlparse(url).path
    assert client.get(path).status_code==200
    assert client.get(path).status_code==200
    assert client.post(path).status_code==302
    with client.session_transaction() as session: assert session['listener_email']=='buyer@example.com'
    assert b'already used' in client.post(path,follow_redirects=True).data

def test_expired_link_is_rejected(app):
    with app.app_context():
        url=issue_magic_link('buyer@example.com');link=db.session.scalar(db.select(MagicLink))
        link.expires_at=now()-timedelta(seconds=1);db.session.commit()
        assert consume_magic_link(url.rsplit('/',1)[-1]) is None

def test_unknown_email_response_matches_buyer(client,app,paid_order):
    valid=client.post('/library',data={'email':'buyer@example.com'},follow_redirects=True)
    unknown=client.post('/library',data={'email':'unknown@example.com'},follow_redirects=True)
    assert b'If this email has purchases' in valid.data and b'If this email has purchases' in unknown.data

def test_full_audio_is_not_public(client):
    assert client.get('/media/public/'+'a'*32).status_code==404
    assert client.get('/static/private.wav').status_code==404
    assert client.get('/media/public/'+'b'*32).status_code==200

def test_private_audio_requires_email_token_and_entitlement(client,app,paid_order):
    with app.app_context():token=media_token('a'*32,'buyer@example.com')
    path='/media/private/'+'a'*32+'?token='+token
    assert client.get(path).status_code==403
    sign_in(client)
    assert client.get(path).status_code==200
    assert client.get(path,headers={'Range':'bytes=0-99'}).status_code==206
    with app.app_context():ent=db.session.scalar(db.select(PurchaseEntitlement));ent.active=False;db.session.commit()
    assert client.get(path).status_code==403

def test_expired_and_tampered_media_tokens(client,app,paid_order):
    sign_in(client)
    with app.app_context():
        with patch('itsdangerous.timed.TimestampSigner.get_timestamp',return_value=1): token=media_token('a'*32,'buyer@example.com')
    assert client.get('/media/private/'+'a'*32+'?token='+token).status_code==403
    assert client.get('/media/private/'+'a'*32+'?token=bad').status_code==403

def test_cannot_use_another_buyers_token(client,app,paid_order):
    sign_in(client)
    with app.app_context():token=media_token('a'*32,'someone@example.com')
    assert client.get('/media/private/'+'a'*32+'?token='+token).status_code==403

def test_progress_saved_and_clamped(client,app,paid_order):
    sign_in(client)
    response=client.post(f'/library/progress/{app.config["TEST_BOOK_ID"]}',json={'media_id':'a'*32,'seconds':10000})
    assert response.status_code==200
    with app.app_context():assert db.session.scalar(db.select(ListeningProgress)).seconds==2
    assert client.get(f'/library/listen/{app.config["TEST_BOOK_ID"]}').status_code==200

@pytest.mark.parametrize('seconds',[-1,'not-a-number',float('nan'),float('inf')])
def test_invalid_progress_is_rejected(client,app,paid_order,seconds):
    sign_in(client)
    assert client.post(f'/library/progress/{app.config["TEST_BOOK_ID"]}',json={'media_id':'a'*32,'seconds':seconds}).status_code==400

def test_logout_revokes_session_streaming(client,app,paid_order):
    sign_in(client)
    assert client.post('/library/logout').status_code==302
    assert client.get(f'/library/listen/{app.config["TEST_BOOK_ID"]}').status_code==403

def test_access_tokens_are_redacted_from_request_logs():
    import logging
    from app.services.logging_service import RedactAccessTokens
    record=logging.LogRecord('werkzeug',20,'',0,'GET /library/access/my-secret-token HTTP/1.1; /media/private/abc?token=media-secret',(),None)
    assert RedactAccessTokens().filter(record)
    assert 'my-secret-token' not in record.getMessage()
    assert 'media-secret' not in record.getMessage()
