from datetime import timedelta
from unittest.mock import MagicMock
from urllib.parse import urlparse

import requests

from app.extensions import db
from app.models import Audiobook, EmailDelivery, Order, now
from app.services.email_service import configured, deliver_pending, queue_access_email
from app.services.stripe_service import create_order, handle_event


def resend(app, monkeypatch, status=200):
    app.config.update(RESEND_API_KEY='re_fixture', RESEND_FROM_EMAIL='MyAudioShelf <books@verified.test>', RESEND_REPLY_TO='support@verified.test')
    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = status
    response.json.return_value = {'id': 'email_fixture'}
    post = MagicMock(return_value=response)
    monkeypatch.setattr('app.services.email_service.requests.post', post)
    return post


def test_payment_sends_receipt_once_and_email_link_downloads(client, app, monkeypatch):
    post = resend(app, monkeypatch)
    with app.app_context():
        order = create_order('buyer@example.com', [db.session.get(Audiobook, app.config['TEST_BOOK_ID'])])
        order.stripe_session_id = 'cs_email'
        db.session.commit()
        event = {'id': 'evt_email', 'type': 'checkout.session.completed', 'data': {'object': {
            'id': 'cs_email', 'metadata': {'order_id': order.id}, 'payment_status': 'paid',
            'amount_total': order.total_minor, 'currency': order.currency, 'payment_intent': 'pi_email'}}}
        assert handle_event(event) == 'processed'
        assert handle_event(event) == 'duplicate'
        event['id'] = 'evt_email_again'
        assert handle_event(event) == 'processed'
        assert post.call_count == 1
        item = db.session.scalar(db.select(EmailDelivery))
        assert item.status == 'sent' and item.provider_message_id == 'email_fixture'
        assert '/library/access/' not in item.body and item.html_body is None
    payload = post.call_args.kwargs['json']
    assert payload['from'] == app.config['RESEND_FROM_EMAIL']
    assert payload['reply_to'] == 'support@verified.test'
    assert 'Test Book' in payload['html'] and 'Total paid' in payload['text']
    assert 'attachments' not in payload
    link = next(line.split(': ', 1)[1] for line in payload['text'].splitlines() if line.startswith('Download the complete audiobook: '))
    parsed = urlparse(link)
    assert client.get(parsed.path + '?' + parsed.query).status_code == 200
    assert client.get(parsed.path + '?' + parsed.query).status_code == 200
    downloaded = client.post(parsed.path, data={'download': app.config['TEST_BOOK_ID']}, follow_redirects=True)
    assert downloaded.status_code == 200
    assert 'attachment' in downloaded.headers['Content-Disposition']
    assert downloaded.data.startswith(b'RIFF')


def test_failed_delivery_retries_same_payload_without_undoing_payment(app, paid_order, monkeypatch):
    post = resend(app, monkeypatch, status=429)
    with app.app_context():
        item = queue_access_email('buyer@example.com', db.session.get(Order, paid_order))
        db.session.commit()
        assert deliver_pending() == 0
        assert item.status == 'queued' and item.attempts == 1
        assert db.session.get(Order, paid_order).status == 'paid'
        first = post.call_args.kwargs
        post.return_value.status_code = 200
        assert deliver_pending() == 1
        assert post.call_args.kwargs == first
        assert deliver_pending() == 0


def test_expired_queued_link_refreshes_before_retry(app, paid_order, monkeypatch):
    post = resend(app, monkeypatch)
    with app.app_context():
        item = queue_access_email('buyer@example.com', db.session.get(Order, paid_order))
        old_key, old_body = item.delivery_key, item.body
        item.link_expires_at = now() - timedelta(seconds=1)
        db.session.commit()
        assert deliver_pending() == 1
        assert post.call_args.kwargs['headers']['Idempotency-Key'] != 'shelf-email/' + old_key
        assert post.call_args.kwargs['json']['text'] != old_body


def test_refunded_order_email_is_cancelled(app, paid_order, monkeypatch):
    post = resend(app, monkeypatch)
    with app.app_context():
        order = db.session.get(Order, paid_order)
        item = queue_access_email(order.email, order)
        order.status = 'refunded'
        db.session.commit()
        assert deliver_pending() == 0
        assert item.status == 'cancelled' and item.html_body is None
        post.assert_not_called()


def test_timeout_keeps_email_queued(app, paid_order, monkeypatch):
    post = resend(app, monkeypatch)
    post.side_effect = requests.Timeout()
    with app.app_context():
        item = queue_access_email('buyer@example.com', db.session.get(Order, paid_order))
        db.session.commit()
        assert deliver_pending() == 0
        assert item.status == 'queued' and item.claimed_until is None
        assert item.last_error == 'Resend connection failed; retry pending.'


def test_missing_sender_leaves_email_queued(app, paid_order, monkeypatch):
    post = resend(app, monkeypatch)
    app.config['RESEND_FROM_EMAIL'] = ''
    with app.app_context():
        assert not configured()
        item = queue_access_email('buyer@example.com', db.session.get(Order, paid_order))
        db.session.commit()
        assert deliver_pending() == 0
        assert item.status == 'queued'
        post.assert_not_called()
    result = app.test_cli_runner().invoke(args=['check-email-config'])
    assert result.exit_code != 0 and 'RESEND_FROM_EMAIL' in result.output


def test_claimed_message_does_not_block_next_queued_email(app, paid_order, monkeypatch):
    post = resend(app, monkeypatch)
    with app.app_context():
        order = db.session.get(Order, paid_order)
        claimed = queue_access_email(order.email, order)
        claimed.created_at = now() - timedelta(minutes=1)
        claimed.claimed_until = now() + timedelta(minutes=2)
        waiting = queue_access_email(order.email, order)
        db.session.commit()
        assert deliver_pending(limit=1) == 1
        assert claimed.status == 'queued' and claimed.attempts == 0
        assert waiting.status == 'sent'
        assert post.call_count == 1
