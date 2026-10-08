import re
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, render_template, redirect, url_for, session, flash, abort, send_file, current_app, g
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy.exc import IntegrityError
from ..extensions import db, limiter
from ..models import (Audiobook, Author, Category, Chapter, MediaAsset, Order, PurchaseEntitlement,
    ProductionEnquiry, AdminUser, AuditLog, AnalyticsEvent, EmailDelivery, NewsletterSubscriber, ListeningProgress, now, uid)
from ..services.access_service import admin_required, normalize_email
from ..services.media_service import store_upload, publication_errors, media_path
from ..services.email_service import queue_access_email
from .main import visible_books

bp = Blueprint('admin', __name__, url_prefix='/admin')
DUMMY_HASH = generate_password_hash('unused-staff-password')

def slugify(value):
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')[:170]

def audit(action, detail):
    db.session.add(AuditLog(admin_id=g.admin.id, action=action, detail=str(detail)[:5000]))

def text(field, limit=180):
    return request.form.get(field, '').strip()[:limit]

@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per 15 minutes', methods=['POST'])
def login():
    if request.method == 'POST':
        user = db.session.scalar(db.select(AdminUser).where(db.func.lower(AdminUser.email) == text('email', 254).lower()))
        password = request.form.get('password', '')
        valid = check_password_hash(user.password_hash if user else DUMMY_HASH, password[:1024])
        if user and user.active and valid and len(password) <= 1024:
            session.clear()
            session['admin_id'] = user.id
            session['admin_version'] = user.session_version
            db.session.add(AuditLog(admin_id=user.id, action='login', detail='Staff sign-in'))
            db.session.commit()
            return redirect(url_for('admin.dashboard'))
        flash('Email or password is incorrect.', 'error')
    return render_template('admin/login.html')

@bp.post('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.home'))

@bp.get('/')
@admin_required()
def dashboard():
    orders = db.session.scalars(db.select(Order).order_by(Order.created_at.desc()).limit(8)).all()
    revenue = db.session.execute(db.select(Order.currency, db.func.sum(Order.total_minor)).where(Order.status == 'paid').group_by(Order.currency)).all()
    counts = {'page_views': db.session.scalar(db.select(db.func.count()).select_from(AnalyticsEvent).where(AnalyticsEvent.kind.like('page_view:%'))),
        'audio_completions': db.session.scalar(db.select(db.func.count()).select_from(AnalyticsEvent).where(AnalyticsEvent.kind == 'audio_complete')),
        'contacts': db.session.scalar(db.select(db.func.count()).select_from(AnalyticsEvent).where(AnalyticsEvent.kind == 'contact_submission')),
        'books': db.session.scalar(db.select(db.func.count()).select_from(Audiobook)),
        'drafts': db.session.scalar(db.select(db.func.count()).select_from(Audiobook).where(Audiobook.state == 'draft')),
        'orders': db.session.scalar(db.select(db.func.count()).select_from(Order)),
        'enquiries': db.session.scalar(db.select(db.func.count()).select_from(ProductionEnquiry).where(ProductionEnquiry.status == 'new')),
        'trailers': db.session.scalar(db.select(db.func.count()).select_from(AnalyticsEvent).where(AnalyticsEvent.kind == 'trailer_play')),
        'subscribers': db.session.scalar(db.select(db.func.count()).select_from(NewsletterSubscriber)),
        'queued_email': db.session.scalar(db.select(db.func.count()).select_from(EmailDelivery).where(EmailDelivery.status == 'queued'))}
    top_titles = db.session.execute(db.select(Audiobook.title, db.func.count(PurchaseEntitlement.id)).join(PurchaseEntitlement).where(PurchaseEntitlement.active.is_(True)).group_by(Audiobook.id).order_by(db.func.count(PurchaseEntitlement.id).desc()).limit(5)).all()
    return render_template('admin/dashboard.html', orders=orders, revenue=revenue, counts=counts, top_titles=top_titles)

@bp.get('/books')
@admin_required()
def books():
    query = db.select(Audiobook).order_by(Audiobook.created_at.desc(), Audiobook.id.desc())
    q = request.args.get('q', '').strip()[:150]
    if q:
        query = query.where(Audiobook.title.ilike('%' + q.replace('%', '\\%').replace('_', '\\_') + '%', escape='\\'))
    page = db.paginate(query, per_page=10, error_out=False)
    return render_template('admin/books.html', books=page.items, page=page, q=q)

@bp.route('/books/new', methods=['GET', 'POST'])
@bp.route('/books/<string:book_id>/edit', methods=['GET', 'POST'])
@admin_required('owner', 'editor')
def edit_book(book_id=None):
    book = db.get_or_404(Audiobook, book_id) if book_id else None
    if request.method == 'POST':
        try:
            title = text('title')
            slug = slugify(text('slug') or title)
            author_name = text('author_name', 150)
            if not all([title, slug, author_name]):
                raise ValueError('Title, slug and author are required.')
            author = db.session.scalar(db.select(Author).where(Author.slug == slugify(author_name)))
            if not author:
                author = Author(name=author_name, slug=slugify(author_name), bio=text('author_bio', 10000))
                db.session.add(author)
            else:
                author.name = author_name
                author.bio = text('author_bio', 10000)
            if not book:
                book = Audiobook(title=title, slug=slug, author=author)
                db.session.add(book)
            book.title, book.slug, book.author = title, slug, author
            for field, limit in {'narrator':250, 'publisher':150, 'synopsis':20000, 'production_notes':10000,
                    'credits':10000, 'transcript':20000, 'language':60, 'age_range':40, 'seo_title':180, 'seo_description':300}.items():
                setattr(book, field, text(field, limit))
            book.production_style = text('production_style', 40)
            if book.production_style not in {'Narrated', 'Immersive', 'Full cast'}:
                raise ValueError('Choose a valid production style.')
            book.currency = text('currency', 3).lower()
            if book.currency not in {'ngn', 'usd', 'gbp', 'eur'}:
                raise ValueError('Currency must be NGN, USD, GBP or EUR.')
            amount = Decimal(request.form.get('price', '0'))
            if not amount.is_finite() or amount < 0 or amount > 10000000 or amount.as_tuple().exponent < -2:
                raise ValueError('Enter a price with at most two decimal places.')
            book.price_minor = int(amount * 100)
            book.duration_minutes = int(request.form.get('duration_minutes') or 0)
            if not 0 <= book.duration_minutes <= 100000:
                raise ValueError('Enter a valid duration.')
            for flag in ['saleable', 'featured', 'hero', 'original', 'children', 'homepage_visible']:
                setattr(book, flag, flag in request.form)
            ids = request.form.getlist('categories')
            book.categories = db.session.scalars(db.select(Category).where(Category.id.in_(ids))).all()
            db.session.flush()
            for kind in ['cover', 'trailer', 'full', 'compare_plain', 'compare_immersive']:
                upload = request.files.get(kind)
                if upload and upload.filename:
                    old = book.asset(kind)
                    store_upload(upload, book, kind)
                    if old:
                        db.session.execute(db.update(ListeningProgress).where(ListeningProgress.media_id == old.id).values(media_id=None, seconds=0))
                        db.session.delete(old)
                        book.media.remove(old)
            # A title and audio file add one ordered chapter per save.
            chapter_file = request.files.get('chapter_audio')
            if chapter_file and chapter_file.filename:
                chapter_title = text('chapter_title')
                if not chapter_title:
                    raise ValueError('Enter a title for the chapter audio.')
                asset = store_upload(chapter_file, book, 'chapter')
                db.session.flush()
                position = max([c.position for c in book.chapters] or [0]) + 1
                book.chapters.append(Chapter(title=chapter_title, position=position, media=asset))
            state = text('state', 20)
            if state not in {'draft', 'published', 'archived'}:
                raise ValueError('Choose a valid publication state.')
            if state == 'published':
                errors = publication_errors(book)
                if errors:
                    raise ValueError(' '.join(errors))
                if not book.published_at:
                    book.published_at = now()
                if book.hero:
                    db.session.execute(db.update(Audiobook).where(Audiobook.id != book.id).values(hero=False))
            book.state = state
            audit('book.saved', f'{book.id}: {book.title} ({state})')
            db.session.commit()
            flash('Audiobook saved.', 'success')
            return redirect(url_for('admin.edit_book', book_id=book.id))
        except (ValueError, InvalidOperation) as error:
            db.session.rollback()
            flash(str(error) if isinstance(error, ValueError) else 'Enter a valid price.', 'error')
        except IntegrityError:
            db.session.rollback()
            flash('That slug is already in use. Choose a unique slug.', 'error')
        book = db.session.get(Audiobook, book_id) if book_id else None
    categories = db.session.scalars(db.select(Category).order_by(Category.position, Category.name)).all()
    return render_template('admin/edit_book.html', book=book, categories=categories)

@bp.get('/books/<string:book_id>/preview')
@admin_required()
def preview(book_id):
    book = db.get_or_404(Audiobook, book_id)
    return render_template('book.html', book=book, related=[], preview=True)

@bp.get('/media/<media_id>')
@admin_required()
def preview_media(media_id):
    asset = db.get_or_404(MediaAsset, media_id)
    if g.admin.role == 'support' and asset.kind not in {'cover', 'trailer', 'compare_plain', 'compare_immersive'}:
        abort(403)
    path = media_path(asset)
    if not path.is_file():
        abort(404)
    response = send_file(path, mimetype=asset.mime_type, conditional=True)
    response.headers['Cache-Control'] = 'private, no-store'
    return response

@bp.post('/chapters/<string:chapter_id>/delete')
@admin_required('owner', 'editor')
def delete_chapter(chapter_id):
    chapter = db.get_or_404(Chapter, chapter_id)
    book = chapter.book
    if book.state == 'published':
        flash('Unpublish the book before removing chapters.', 'error')
        return redirect(url_for('admin.edit_book', book_id=book.id))
    media = chapter.media
    audit('chapter.deleted', f'{book.id}: {chapter.title}')
    db.session.delete(chapter)
    db.session.flush()
    db.session.execute(db.update(ListeningProgress).where(ListeningProgress.media_id == media.id).values(media_id=None, seconds=0))
    db.session.delete(media)
    db.session.commit()
    return redirect(url_for('admin.edit_book', book_id=book.id))

@bp.post('/chapters/<string:chapter_id>/move')
@admin_required('owner', 'editor')
def move_chapter(chapter_id):
    chapter = db.get_or_404(Chapter, chapter_id)
    siblings = chapter.book.chapters
    index = siblings.index(chapter)
    destination = index + (-1 if request.form.get('direction') == 'up' else 1)
    if 0 <= destination < len(siblings):
        other = siblings[destination]
        previous = chapter.position
        chapter.position = max(c.position for c in siblings) + 1000
        db.session.flush()
        other_pos = other.position
        other.position = previous
        db.session.flush()
        chapter.position = other_pos
        audit('chapter.moved', f'{chapter.book_id}: {chapter.title}')
        db.session.commit()
    return redirect(url_for('admin.edit_book', book_id=chapter.book_id))

@bp.route('/categories', methods=['GET', 'POST'])
@admin_required('owner', 'editor')
def categories():
    if request.method == 'POST':
        name = text('name', 80)
        slug = slugify(name)
        if name and slug:
            try:
                db.session.add(Category(name=name, slug=slug))
                audit('category.created', name)
                db.session.commit()
                flash('Genre added.', 'success')
            except IntegrityError:
                db.session.rollback()
                flash('That genre already exists.', 'error')
        return redirect(url_for('admin.categories'))
    page = db.paginate(db.select(Category).order_by(Category.name), per_page=10, error_out=False)
    return render_template('admin/categories.html', categories=page.items, page=page)

@bp.get('/orders')
@admin_required('owner', 'support')
def orders():
    page = db.paginate(db.select(Order).order_by(Order.created_at.desc()), per_page=10, error_out=False)
    return render_template('admin/orders.html', page=page)

@bp.get('/orders/<order_id>')
@admin_required('owner', 'support')
def order_detail(order_id):
    order = db.get_or_404(Order, order_id)
    entitlements = db.session.scalars(db.select(PurchaseEntitlement).where(PurchaseEntitlement.order_id == order.id)).all()
    return render_template('admin/order.html', order=order, entitlements=entitlements)

@bp.post('/entitlements/<string:entitlement_id>')
@admin_required('owner', 'support')
def entitlement(entitlement_id):
    entitlement = db.get_or_404(PurchaseEntitlement, entitlement_id)
    action = text('action', 20)
    reason = text('reason', 500)
    if not reason:
        flash('Enter a reason for changing access.', 'error')
        return redirect(url_for('admin.order_detail', order_id=entitlement.order_id))
    if action == 'revoke':
        entitlement.active = False
    elif action == 'restore':
        order = db.session.get(Order, entitlement.order_id)
        if order.status != 'paid':
            abort(400)
        entitlement.active = True
    elif action == 'reissue' and entitlement.active:
        queue_access_email(entitlement.email)
    else:
        abort(400)
    audit('entitlement.' + action, f'{entitlement.id}: {reason}')
    db.session.commit()
    flash('Access updated; any requested email is queued for delivery.', 'success')
    return redirect(url_for('admin.order_detail', order_id=entitlement.order_id))

@bp.route('/enquiries', methods=['GET', 'POST'])
@admin_required('owner', 'editor', 'support')
def enquiries():
    if request.method == 'POST':
        from ..services.identity_service import resolve_id
        item = db.get_or_404(ProductionEnquiry, resolve_id('production_enquiry', request.form.get('id')))
        state = text('status', 30)
        if state not in {'new', 'reviewing', 'contacted', 'accepted', 'closed'}:
            abort(400)
        item.status, item.notes = state, text('notes', 10000)
        audit('enquiry.updated', item.id)
        db.session.commit()
        return redirect(url_for('admin.enquiries'))
    page = db.paginate(db.select(ProductionEnquiry).order_by(ProductionEnquiry.created_at.desc()), per_page=10, error_out=False)
    return render_template('admin/enquiries.html', page=page)

@bp.route('/staff', methods=['GET', 'POST'])
@admin_required('owner')
def staff():
    if request.method == 'POST':
        try:
            email = normalize_email(text('email', 254))
            password = request.form.get('password', '')
            role = text('role', 20)
            if len(password) < 12 or role not in {'owner', 'editor', 'support'}:
                raise ValueError('Choose a valid role and a password of at least 12 characters.')
            db.session.add(AdminUser(email=email, password_hash=generate_password_hash(password), role=role))
            audit('staff.created', f'{email}: {role}')
            db.session.commit()
            flash('Staff member created.', 'success')
        except ValueError as error:
            flash(str(error), 'error')
        except IntegrityError:
            db.session.rollback()
            flash('That staff email already exists.', 'error')
        return redirect(url_for('admin.staff'))
    page = db.paginate(db.select(AdminUser).order_by(AdminUser.email), per_page=10, error_out=False)
    return render_template('admin/staff.html', staff=page.items, page=page)

@bp.post('/staff/<string:user_id>/toggle')
@admin_required('owner')
def toggle_staff(user_id):
    user = db.get_or_404(AdminUser, user_id)
    if user.id == g.admin.id:
        abort(400)
    user.active = not user.active
    user.session_version = uid()
    audit('staff.toggled', f'{user.email}: {user.active}')
    db.session.commit()
    return redirect(url_for('admin.staff'))

@bp.get('/audit')
@admin_required('owner')
def audit_history():
    page = db.paginate(db.select(AuditLog).order_by(AuditLog.created_at.desc()), per_page=10, error_out=False)
    return render_template('admin/audit.html', page=page)

@bp.get('/outbox')
@admin_required('owner')
def outbox():
    if current_app.config['PRODUCTION']:
        abort(404)
    page = db.paginate(db.select(EmailDelivery).order_by(EmailDelivery.created_at.desc()), per_page=10, error_out=False)
    return render_template('admin/outbox.html', page=page)


@bp.get('/enquiries/<string:enquiry_id>/manuscript')
@admin_required('owner','editor')
def manuscript(enquiry_id):
    from pathlib import Path
    item=db.get_or_404(ProductionEnquiry,enquiry_id)
    if not item.attachment_key:abort(404)
    from ..services.storage_service import path_for
    path=path_for(item.attachment_key)
    if not path.is_file():abort(404)
    response=send_file(path,as_attachment=True,download_name=item.attachment_name)
    response.headers['Cache-Control']='private, no-store'
    return response
