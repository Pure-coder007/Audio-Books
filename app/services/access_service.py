import hashlib
import secrets
from datetime import timedelta
from functools import wraps
from flask import current_app, session, abort, redirect, url_for, request, g
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from ..extensions import db
from ..models import MagicLink, PurchaseEntitlement, AdminUser, now

def normalize_email(value):
    import re
    value = (value or '').strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        raise ValueError('Enter a valid email address.')
    return value

def issue_magic_link(email):
    token = secrets.token_urlsafe(32)
    db.session.add(MagicLink(token_hash=hashlib.sha256(token.encode()).hexdigest(), email=email,
        expires_at=now() + timedelta(seconds=current_app.config['MAGIC_LINK_TTL'])))
    return current_app.config['BASE_URL'] + '/library/access/' + token

def consume_magic_link(token):
    digest = hashlib.sha256(token.encode()).hexdigest()
    link = db.session.scalar(db.select(MagicLink).where(MagicLink.token_hash == digest))
    if not link:
        return None
    result = db.session.execute(db.update(MagicLink).where(MagicLink.id == link.id,
        MagicLink.used_at.is_(None), MagicLink.expires_at > now()).values(used_at=now()))
    db.session.commit()
    return link.email if result.rowcount == 1 else None

def has_access(email, book_id):
    if not email:
        return False
    return db.session.scalar(db.select(PurchaseEntitlement.id).where(
        PurchaseEntitlement.email == email, PurchaseEntitlement.book_id == book_id,
        PurchaseEntitlement.active.is_(True))) is not None

def media_token(media_id, email):
    return URLSafeTimedSerializer(current_app.secret_key, salt='private-audio').dumps({'media': media_id, 'email': email})

def verify_media_token(token, media_id):
    try:
        data = URLSafeTimedSerializer(current_app.secret_key, salt='private-audio').loads(token,
            max_age=current_app.config['MEDIA_TOKEN_TTL'])
    except (BadSignature, SignatureExpired):
        abort(403)
    if data.get('media') != media_id or data.get('email') != session.get('listener_email'):
        abort(403)
    return data['email']

def admin_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            admin = db.session.get(AdminUser, session.get('admin_id')) if session.get('admin_id') else None
            if not admin or not admin.active or session.get('admin_version') != admin.session_version:
                return redirect(url_for('admin.login'))
            if roles and admin.role not in roles:
                abort(403)
            g.admin = admin
            return fn(*args, **kwargs)
        return wrapped
    return decorator
