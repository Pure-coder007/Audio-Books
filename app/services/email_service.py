import smtplib
import ssl
from email.message import EmailMessage
from flask import current_app
from ..extensions import db
from ..models import EmailDelivery
from .access_service import issue_magic_link

def queue_access_email(email):
    link = issue_magic_link(email)
    db.session.add(EmailDelivery(recipient=email, subject='Your MyAudioShelf listening link',
        body=f'Your shelf is ready. Open this single-use link within 15 minutes:\n\n{link}\n\nIf it expires, request a new link from My Purchases.\n\nMyAudioShelf'))

def deliver_pending():
    """Durable outbox: called by scheduled CLI, never during a Stripe transaction."""
    if not current_app.config['MAIL_HOST']:
        return 0
    queued = db.session.scalars(db.select(EmailDelivery).where(EmailDelivery.status == 'queued').order_by(EmailDelivery.id).limit(100)).all()
    sent = 0
    for item in queued:
        try:
            msg = EmailMessage()
            msg['Subject'] = item.subject
            msg['From'] = current_app.config['MAIL_FROM']
            msg['To'] = item.recipient
            msg.set_content(item.body)
            with smtplib.SMTP(current_app.config['MAIL_HOST'], current_app.config['MAIL_PORT'], timeout=15) as smtp:
                if current_app.config['MAIL_USE_TLS']:
                    smtp.starttls(context=ssl.create_default_context())
                if current_app.config['MAIL_USERNAME']:
                    smtp.login(current_app.config['MAIL_USERNAME'], current_app.config['MAIL_PASSWORD'])
                smtp.send_message(msg)
            item.status = 'sent'
            item.body = '[Delivered; access link removed]'
            sent += 1
        except (OSError, smtplib.SMTPException):
            current_app.logger.warning('Email delivery failed; retained for retry (id=%s).', item.id)
        item.attempts += 1
        db.session.commit()
    return sent
