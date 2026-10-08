from datetime import datetime, timezone
from uuid import uuid4
from .extensions import db

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def uid():
    return uuid4().hex

book_categories = db.Table('book_categories',
    db.Column('book_id', db.String(32), db.ForeignKey('audiobook.id'), primary_key=True),
    db.Column('category_id', db.String(32), db.ForeignKey('category.id'), primary_key=True))

class Author(db.Model):
    id = db.Column(db.String(32), primary_key=True, default=uid)
    name = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(180), unique=True, nullable=False)
    bio = db.Column(db.Text, default='')
    books = db.relationship('Audiobook', back_populates='author')

class Category(db.Model):
    id = db.Column(db.String(32), primary_key=True, default=uid)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    position = db.Column(db.Integer, default=0)

class Audiobook(db.Model):
    id = db.Column(db.String(32), primary_key=True, default=uid)
    slug = db.Column(db.String(180), unique=True, nullable=False)
    title = db.Column(db.String(180), nullable=False)
    author_id = db.Column(db.String(32), db.ForeignKey('author.id'), nullable=False)
    author = db.relationship('Author', back_populates='books')
    narrator = db.Column(db.String(250), default='')
    publisher = db.Column(db.String(150), default='')
    synopsis = db.Column(db.Text, default='')
    production_notes = db.Column(db.Text, default='')
    credits = db.Column(db.Text, default='')
    transcript = db.Column(db.Text, default='')
    language = db.Column(db.String(60), default='English')
    age_range = db.Column(db.String(40), default='')
    duration_minutes = db.Column(db.Integer, default=0)
    production_style = db.Column(db.String(40), default='Narrated')
    price_minor = db.Column(db.Integer, default=0, nullable=False)
    currency = db.Column(db.String(3), default='ngn', nullable=False)
    state = db.Column(db.String(20), default='draft', nullable=False)
    saleable = db.Column(db.Boolean, default=True)
    featured = db.Column(db.Boolean, default=False)
    hero = db.Column(db.Boolean, default=False)
    original = db.Column(db.Boolean, default=False)
    children = db.Column(db.Boolean, default=False)
    is_demo = db.Column(db.Boolean, default=False)
    homepage_visible = db.Column(db.Boolean, default=True)
    seo_title = db.Column(db.String(180), default='')
    seo_description = db.Column(db.String(300), default='')
    published_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=now)
    categories = db.relationship('Category', secondary=book_categories)
    media = db.relationship('MediaAsset', back_populates='book', cascade='all, delete-orphan')
    chapters = db.relationship('Chapter', back_populates='book', order_by='Chapter.position', cascade='all, delete-orphan')
    def asset(self, kind):
        return next((m for m in self.media if m.kind == kind), None)
    @property
    def duration_label(self):
        h, m = divmod(self.duration_minutes or 0, 60)
        return f'{h}h {m:02d}m' if h else f'{m}m'
    @property
    def cover_url(self):
        from flask import url_for
        media = self.asset('cover')
        return url_for('main.public_media', media_id=media.id) if media else url_for('static', filename=f'covers/{self.slug}.svg') if self.is_demo else url_for('static', filename='covers/placeholder.svg')

class MediaAsset(db.Model):
    id = db.Column(db.String(32), primary_key=True, default=uid)
    book_id = db.Column(db.String(32), db.ForeignKey('audiobook.id'), nullable=False)
    book = db.relationship('Audiobook', back_populates='media')
    kind = db.Column(db.String(20), nullable=False)
    storage_key = db.Column(db.String(200), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    size_bytes = db.Column(db.BigInteger, default=0)
    duration_seconds = db.Column(db.Float, default=0)

class Chapter(db.Model):
    id = db.Column(db.String(32), primary_key=True, default=uid)
    book_id = db.Column(db.String(32), db.ForeignKey('audiobook.id'), nullable=False)
    book = db.relationship('Audiobook', back_populates='chapters')
    title = db.Column(db.String(180), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    media_id = db.Column(db.String(32), db.ForeignKey('media_asset.id'), nullable=False)
    media = db.relationship('MediaAsset')
    __table_args__ = (db.UniqueConstraint('book_id', 'position'),)

class Order(db.Model):
    id = db.Column(db.String(32), primary_key=True, default=uid)
    email = db.Column(db.String(254), nullable=False, index=True)
    total_minor = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    status = db.Column(db.String(30), default='pending')
    stripe_session_id = db.Column(db.String(255), unique=True)
    stripe_payment_id = db.Column(db.String(255), index=True)
    created_at = db.Column(db.DateTime, default=now)
    paid_at = db.Column(db.DateTime)
    items = db.relationship('OrderItem', back_populates='order', cascade='all, delete-orphan')

class OrderItem(db.Model):
    id = db.Column(db.String(32), primary_key=True, default=uid)
    order_id = db.Column(db.String(32), db.ForeignKey('order.id'), nullable=False)
    order = db.relationship('Order', back_populates='items')
    book_id = db.Column(db.String(32), db.ForeignKey('audiobook.id'), nullable=False)
    book = db.relationship('Audiobook')
    title = db.Column(db.String(180), nullable=False)
    price_minor = db.Column(db.Integer, nullable=False)

class PurchaseEntitlement(db.Model):
    id = db.Column(db.String(32), primary_key=True, default=uid)
    email = db.Column(db.String(254), nullable=False, index=True)
    book_id = db.Column(db.String(32), db.ForeignKey('audiobook.id'), nullable=False)
    book = db.relationship('Audiobook')
    order_id = db.Column(db.String(32), db.ForeignKey('order.id'), nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=now)
    __table_args__ = (db.UniqueConstraint('email', 'book_id'),)

class MagicLink(db.Model):
    id = db.Column(db.String(32), primary_key=True, default=uid)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(254), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)

class ListeningProgress(db.Model):
    id = db.Column(db.String(32), primary_key=True, default=uid)
    email = db.Column(db.String(254), nullable=False)
    book_id = db.Column(db.String(32), db.ForeignKey('audiobook.id'), nullable=False)
    media_id = db.Column(db.String(32), db.ForeignKey('media_asset.id'))
    seconds = db.Column(db.Float, default=0)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)
    __table_args__ = (db.UniqueConstraint('email', 'book_id'),)

class AdminUser(db.Model):
    id = db.Column(db.String(32), primary_key=True, default=uid)
    email = db.Column(db.String(254), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='owner')
    active = db.Column(db.Boolean, default=True)
    session_version = db.Column(db.String(32), default=uid)

class AuditLog(db.Model):
    id = db.Column(db.String(32), primary_key=True, default=uid)
    admin_id = db.Column(db.String(32), db.ForeignKey('admin_user.id'))
    action = db.Column(db.String(100), nullable=False)
    detail = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=now)

class StripeEvent(db.Model):
    id = db.Column(db.String(255), primary_key=True)
    event_type = db.Column(db.String(100), nullable=False)
    processed_at = db.Column(db.DateTime, default=now)

class ProductionEnquiry(db.Model):
    enquiry_type = db.Column(db.String(30), default='author', server_default='author', nullable=False)
    project_details = db.Column(db.Text, default='{}')
    attachment_key = db.Column(db.String(200))
    attachment_name = db.Column(db.String(180))
    @property
    def details(self):
        import json
        return json.loads(self.project_details or '{}')
    id = db.Column(db.String(32), primary_key=True, default=uid)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default='new')
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=now)

class NewsletterSubscriber(db.Model):
    first_name = db.Column(db.String(100), default='')
    id = db.Column(db.String(32), primary_key=True, default=uid)
    email = db.Column(db.String(254), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=now)

class AnalyticsEvent(db.Model):
    id = db.Column(db.String(32), primary_key=True, default=uid)
    book_id = db.Column(db.String(32), db.ForeignKey('audiobook.id'))
    kind = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, default=now)

class EmailDelivery(db.Model):
    html_body = db.Column(db.Text)
    order_id = db.Column(db.String(32), db.ForeignKey('order.id'))
    link_expires_at = db.Column(db.DateTime)
    delivery_key = db.Column(db.String(32), nullable=False, default=uid)
    claimed_until = db.Column(db.DateTime)
    provider_message_id = db.Column(db.String(255))
    sent_at = db.Column(db.DateTime)
    last_error = db.Column(db.String(100))
    id = db.Column(db.String(32), primary_key=True, default=uid)
    recipient = db.Column(db.String(254), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='queued')
    attempts = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=now)

class PaymentRefund(db.Model):
    payment_intent_id = db.Column(db.String(255), primary_key=True)
    stripe_event_id = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=now)

class Customer(db.Model):
    id = db.Column(db.String(32), primary_key=True, default=uid)
    email = db.Column(db.String(254), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=now)


class LegacyUuidMap(db.Model):
    __tablename__ = 'legacy_uuid_map'
    table_name = db.Column(db.String(80), primary_key=True)
    legacy_id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(32), nullable=False)
