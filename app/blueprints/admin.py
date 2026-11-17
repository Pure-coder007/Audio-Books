import re
import math
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, render_template, redirect, url_for, session, flash, abort, send_file, current_app, g
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from ..extensions import db, limiter
from ..models import (Audiobook, Author, Category, Chapter, MediaAsset, Order, PurchaseEntitlement,
    ProductionEnquiry, AdminUser, AuditLog, AuthorAccount, AnalyticsEvent, EmailDelivery, NewsletterSubscriber, ListeningProgress, BOOK_SECTIONS, now, uid)
from ..services.access_service import admin_required, normalize_email
from ..services.media_service import store_upload, publication_field_errors, media_path, AUDIO_ACCEPT
from ..services.email_service import queue_access_email
from ..services.catalog_service import times_bought, delete_audiobook
from ..content.admin_tour import TOUR_PAGES, TOURS, TOUR_SIGN_INS
from ..content.languages import BOOK_LANGUAGES, BOOK_LANGUAGE_NAMES
from .main import visible_books

bp = Blueprint('admin', __name__, url_prefix='/admin')
DUMMY_HASH = generate_password_hash('unused-staff-password')

def slugify(value):
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')[:170]

def audit(action, detail):
    db.session.add(AuditLog(admin_id=g.admin.id, action=action, detail=str(detail)[:5000]))

class BookValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__('Please correct the highlighted fields.')


def text(field, limit=180):
    return request.form.get(field, '').strip()[:limit]

def tour_sign_in(user):
    """This sign-in's number for the guided tour, or 0 once the tour is turned off."""
    logs = db.select(db.func.count()).select_from(AuditLog).where(AuditLog.admin_id == user.id)
    if db.session.scalar(logs.where(AuditLog.action == 'tour.dismissed')):
        return 0
    return db.session.scalar(logs.where(AuditLog.action == 'login'))

@bp.context_processor
def guided_tour():
    page = TOUR_PAGES.get(request.endpoint)
    if not page or not getattr(g, 'admin', None):
        return {'tour': None}
    sign_in = session.get('tour_sign_in', 0)
    auto = 0 < sign_in <= TOUR_SIGN_INS and not session.get('tour_skipped') and page not in session.get('tour_seen', [])
    return {'tour': {'page': page, 'steps': TOURS[page], 'auto': auto, 'sign_in': sign_in if auto else 0,
        'sign_ins': TOUR_SIGN_INS, 'endpoint': url_for('admin.tour')}}

@bp.post('/tour')
@admin_required()
def tour():
    data = request.get_json(silent=True) or {}
    action, page = data.get('action'), data.get('page')
    if action not in {'seen', 'skip', 'never'} or page not in TOURS:
        abort(400)
    if action == 'seen':
        session['tour_seen'] = list(dict.fromkeys(session.get('tour_seen', []) + [page]))
    elif action == 'skip':
        session['tour_skipped'] = True
    else:
        session['tour_sign_in'] = 0
        audit('tour.dismissed', 'Guided tour turned off')
        db.session.commit()
    return {'ok': True}

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
            session['tour_sign_in'] = tour_sign_in(user)
            return redirect(url_for('admin.dashboard'))
        flash('Email or password is incorrect.', 'error')
    return render_template('admin/login.html')

STAFF_MIN_PASSWORD = 12

@bp.route('/forgot', methods=['GET', 'POST'])
@limiter.limit('5 per 15 minutes', methods=['POST'])
def forgot():
    from ..services import password_reset_service as resets
    if request.method == 'POST':
        try:
            email = normalize_email(request.form.get('email'))
        except ValueError:
            flash('Enter your staff email address.', 'error')
            return render_template('admin/forgot.html'), 400
        return resets.after_response(redirect(url_for('admin.forgot', sent=1)), resets.request_reset, 'staff', email)
    return render_template('admin/forgot.html', sent=request.args.get('sent') == '1')

@bp.route('/reset/<token>', methods=['GET', 'POST'])
@limiter.limit('10 per 15 minutes', methods=['POST'])
def reset_password(token):
    from ..services import password_reset_service as resets
    _, user = resets.valid_reset('staff', token)
    if not user:
        return render_template('admin/reset.html', expired=True), 410
    error = None
    if request.method == 'POST':
        password, confirm = request.form.get('password', ''), request.form.get('confirm', '')
        if not STAFF_MIN_PASSWORD <= len(password) <= 128:
            error = f'Use {STAFF_MIN_PASSWORD} to 128 characters.'
        elif password != confirm:
            error = 'The two passwords don’t match.'
        else:
            user = resets.complete('staff', token, password)
            if not user:
                return render_template('admin/reset.html', expired=True), 410
            session.clear()
            flash('Your password has been changed. Sign in with your new password.', 'success')
            return resets.after_response(redirect(url_for('admin.login')), resets.notify_changed, 'staff', user.id)
    return render_template('admin/reset.html', user=user, error=error, min_password=STAFF_MIN_PASSWORD), 400 if error else 200

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
        'app_installs': db.session.scalar(db.select(db.func.count()).select_from(AnalyticsEvent).where(AnalyticsEvent.kind == 'app_install')),
        'books': db.session.scalar(db.select(db.func.count()).select_from(Audiobook)),
        'drafts': db.session.scalar(db.select(db.func.count()).select_from(Audiobook).where(Audiobook.state == 'draft')),
        'orders': db.session.scalar(db.select(db.func.count()).select_from(Order)),
        'enquiries': db.session.scalar(db.select(db.func.count()).select_from(ProductionEnquiry).where(ProductionEnquiry.status == 'new')),
        'trailers': db.session.scalar(db.select(db.func.count()).select_from(AnalyticsEvent).where(AnalyticsEvent.kind == 'trailer_play')),
        'subscribers': db.session.scalar(db.select(db.func.count()).select_from(NewsletterSubscriber)),
        'author_accounts': db.session.scalar(db.select(db.func.count()).select_from(AuthorAccount)),
        'queued_email': db.session.scalar(db.select(db.func.count()).select_from(EmailDelivery).where(EmailDelivery.status == 'queued'))}
    top_titles = db.session.execute(db.select(Audiobook.title, db.func.count(PurchaseEntitlement.id)).join(PurchaseEntitlement).where(PurchaseEntitlement.active.is_(True)).group_by(Audiobook.id).order_by(db.func.count(PurchaseEntitlement.id).desc()).limit(5)).all()
    # What keeps published pages out of Google, or makes them thin, with a link to fix each one.
    live = db.session.scalars(visible_books().where(Audiobook.is_demo.is_(False)).order_by(Audiobook.title)).all()
    search = {'hidden': [b for b in live if not b.indexable], 'no_narrator': [b for b in live if not b.coming_soon and not b.narrator],
        'no_bio': list({b.author.slug: b for b in live if not (b.author.bio or '').strip()}.values())}
    return render_template('admin/dashboard.html', orders=orders, revenue=revenue, counts=counts, top_titles=top_titles, search=search)

@bp.get('/books')
@admin_required()
def books():
    query = db.select(Audiobook).order_by(Audiobook.created_at.desc(), Audiobook.id.desc())
    q = request.args.get('q', '').strip()[:150]
    if q:
        query = query.where(Audiobook.title.ilike('%' + q.replace('%', '\\%').replace('_', '\\_') + '%', escape='\\'))
    view = request.args.get('view', '')
    if view == 'featured':
        query = query.where(Audiobook.featured.is_(True))
    elif view == 'coming_soon':
        query = query.where(Audiobook.featured.is_(True), Audiobook.price_minor <= 0)
    elif view in {'translated', 'reviewed'}:
        query = query.where(Audiobook.section == view)
    else:
        view = ''
    page = db.paginate(query, per_page=10, error_out=False)
    return render_template('admin/books.html', books=page.items, page=page, q=q, view=view)

@bp.route('/books/new', methods=['GET', 'POST'])
@bp.route('/books/<string:book_id>/edit', methods=['GET', 'POST'])
@admin_required('owner', 'editor')
def edit_book(book_id=None):
    book = db.get_or_404(Audiobook, book_id) if book_id else None
    field_errors = {}
    active_field = 'title'
    if request.method == 'POST':
        try:
            title = text('title')
            author_name = text('author_name', 150)
            errors = {}
            if not title:
                errors['title'] = 'Enter the audiobook title.'
            if not author_name:
                errors['author_name'] = 'Enter the author name.'
            try:
                # A blank price is allowed: featured titles without one are shown as Coming soon.
                amount = Decimal(request.form.get('price', '').strip() or '0')
                if not amount.is_finite() or amount < 0 or amount > 10000000 or amount.as_tuple().exponent < -2:
                    errors['price'] = 'Enter a price between £0 and £10,000,000 with at most two decimal places.'
            except InvalidOperation:
                errors['price'] = 'Enter a valid price in pounds, for example 14.99.'
            style = request.form.get('production_style', book.production_style if book else 'Narrated')
            if style not in {'Narrated', 'Immersive', 'Full cast'}:
                errors['production_style'] = 'Choose a valid production style.'
            # Books keep a language from before the list existed until it is changed.
            if text('language', 60) not in BOOK_LANGUAGE_NAMES and not (book and text('language', 60) == book.language):
                errors['language'] = 'Choose the language from the list.'
            section = request.form.get('section', book.section if book else 'shelf')
            if section not in BOOK_SECTIONS:
                errors['section'] = 'Choose where this book is listed.'
            state = text('state', 20)
            if state not in {'draft', 'published', 'archived'}:
                errors['state'] = 'Choose Draft, Published or Archived.'
            chapter_file = request.files.get('chapter_audio')
            if chapter_file and chapter_file.filename and not text('chapter_title'):
                errors['chapter_title'] = 'Enter a title for the chapter audio.'
            if text('chapter_title') and not (chapter_file and chapter_file.filename):
                errors['chapter_audio'] = 'Select an audio file for this chapter.'
            if errors:
                raise BookValidationError(errors)
            slug = book.slug if book else (slugify(title) or 'audiobook')
            if not book and db.session.scalar(db.select(Audiobook.id).where(Audiobook.slug == slug)):
                slug += '-' + uid()[:8]
            author = db.session.scalar(db.select(Author).where(Author.slug == slugify(author_name)))
            if not author:
                author = Author(name=author_name, slug=slugify(author_name), bio=text('author_bio', 10000))
                db.session.add(author)
            else:
                author.name = author_name
                # A new book's empty biography box must not erase the biography the author already has.
                if text('author_bio', 10000) or (book and book.author_id == author.id and 'author_bio' in request.form):
                    author.bio = text('author_bio', 10000)
            if not book:
                book = Audiobook(title=title, slug=slug, author=author)
                db.session.add(book)
            book.title, book.slug, book.author = title, slug, author
            for field, limit in {'narrator':250, 'publisher':150, 'synopsis':20000, 'production_notes':10000,
                    'credits':10000, 'transcript':20000, 'language':60, 'age_range':40, 'seo_title':180, 'seo_description':300}.items():
                if field in request.form:
                    setattr(book, field, text(field, limit))
            book.production_style = style
            book.section = section
            book.currency = 'gbp'
            book.price_minor = int(amount * 100)
            for flag in ['featured', 'hero', 'homepage_visible']:
                setattr(book, flag, flag in request.form)
            book.saleable = book.price_minor > 0
            ids = request.form.getlist('categories')
            book.categories = db.session.scalars(db.select(Category).where(Category.id.in_(ids))).all()
            db.session.flush()
            for kind in ['cover', 'trailer', 'full', 'compare_plain', 'compare_immersive']:
                upload = request.files.get(kind)
                if upload and upload.filename:
                    old = book.asset(kind)
                    active_field = kind
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
                    raise BookValidationError({'chapter_title': 'Enter a title for the chapter audio.'})
                active_field = 'chapter_audio'
                asset = store_upload(chapter_file, book, 'chapter')
                db.session.flush()
                position = max([c.position for c in book.chapters] or [0]) + 1
                book.chapters.append(Chapter(title=chapter_title, position=position, media=asset))
            tracks = [c.media for c in book.chapters] if book.chapters else [book.asset('full')]
            seconds = sum(asset.duration_seconds or 0 for asset in tracks if asset)
            if seconds:
                book.duration_minutes = max(1, math.ceil(seconds / 60))
            if state == 'published':
                errors = publication_field_errors(book)
                if errors:
                    raise BookValidationError(errors)
                if not book.published_at:
                    book.published_at = now()
                if book.hero:
                    db.session.execute(db.update(Audiobook).where(Audiobook.id != book.id).values(hero=False))
            book.state = state
            audit('book.saved', f'{book.id}: {book.title} ({state})')
            db.session.commit()
            flash('Audiobook saved. It is on the Featured shelf as Coming soon.' if state == 'published' and book.coming_soon else 'Audiobook saved.', 'success')
            return redirect(url_for('admin.edit_book', book_id=book.id))
        except BookValidationError as error:
            db.session.rollback()
            field_errors = error.errors
        except (ValueError, InvalidOperation) as error:
            db.session.rollback()
            field_errors = {active_field: str(error) if isinstance(error, ValueError) else 'Enter a valid price in pounds.'}
        except IntegrityError:
            db.session.rollback()
            field_errors = {'title': 'This audiobook could not be saved because its details conflict with an existing record. Try a different title.'}
        book = db.session.get(Audiobook, book_id) if book_id else None
    categories = db.session.scalars(db.select(Category).order_by(Category.position, Category.name)).all()
    return render_template('admin/edit_book.html', book=book, categories=categories, field_errors=field_errors, audio_accept=AUDIO_ACCEPT,
        languages=BOOK_LANGUAGES, known_languages=BOOK_LANGUAGE_NAMES, sections=BOOK_SECTIONS)

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

@bp.post('/books/<string:book_id>/visibility')
@admin_required('owner', 'editor')
def book_visibility(book_id):
    """Unpublish takes a book off the storefront; buyers keep it in their library. Publish puts it back after the usual checks."""
    book = db.get_or_404(Audiobook, book_id)
    back = request.form.get('next') if request.form.get('next', '').startswith('/admin/') else url_for('admin.books')
    if request.form.get('action') == 'publish':
        errors = publication_field_errors(book)
        if errors:
            flash(f'“{book.title}” can’t be published yet: ' + ' '.join(errors.values()), 'error')
            return redirect(url_for('admin.edit_book', book_id=book.id))
        book.state = 'published'
        book.published_at = book.published_at or now()
        audit('book.published', f'{book.id}: {book.title}')
        flash(f'“{book.title}” is published and back on the storefront.', 'success')
    else:
        book.state = 'draft'
        audit('book.unpublished', f'{book.id}: {book.title}')
        flash(f'“{book.title}” is unpublished. It is hidden from the storefront; anyone who bought it still has it in their library.', 'success')
    db.session.commit()
    return redirect(back)

@bp.route('/books/<string:book_id>/delete', methods=['GET', 'POST'])
@admin_required('owner', 'editor')
def delete_book(book_id):
    book = db.get_or_404(Audiobook, book_id)
    # A bought book stays on record so receipts and listeners' libraries keep working.
    bought = times_bought(book)
    if request.method == 'POST' and not bought:
        title = book.title
        audit('book.deleted', f'{book.id}: {title}')
        delete_audiobook(book)
        db.session.commit()
        flash(f'“{title}” has been deleted.', 'success')
        return redirect(url_for('admin.books'))
    return render_template('admin/delete_book.html', book=book, bought=bought)

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
    field_errors = {}
    if request.method == 'POST':
        name = text('name', 80)
        slug = slugify(name)
        if not name or not slug:
            field_errors['name'] = 'Genre name: enter a name containing letters or numbers.'
        else:
            try:
                db.session.add(Category(name=name, slug=slug))
                audit('category.created', name)
                db.session.commit()
                flash('Genre added.', 'success')
                return redirect(url_for('admin.categories'))
            except IntegrityError:
                db.session.rollback()
                field_errors['name'] = 'Genre name: that genre already exists.'
    page = db.paginate(db.select(Category).order_by(Category.name), per_page=10, error_out=False)
    return render_template('admin/categories.html', categories=page.items, page=page, field_errors=field_errors)

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

@bp.get('/authors')
@admin_required('owner', 'support')
def author_accounts():
    from ..content.plans import PLANS
    page = db.paginate(db.select(AuthorAccount).options(selectinload(AuthorAccount.projects)).order_by(AuthorAccount.created_at.desc()), per_page=25, error_out=False)
    plan_counts = dict(db.session.execute(db.select(AuthorAccount.plan, db.func.count()).group_by(AuthorAccount.plan)).all())
    return render_template('admin/authors.html', page=page, plans=PLANS, plan_counts=plan_counts)

@bp.route('/staff', methods=['GET', 'POST'])
@admin_required('owner')
def staff():
    field_errors = {}
    if request.method == 'POST':
        try:
            email = normalize_email(text('email', 254))
        except ValueError:
            field_errors['email'] = 'Email: enter a valid email address.'
        password = request.form.get('password', '')
        role = text('role', 20)
        if len(password) < 12:
            field_errors['password'] = 'Password: use at least 12 characters.'
        if role not in {'owner', 'editor', 'support'}:
            field_errors['role'] = 'Role: choose Owner, Editor or Support.'
        if not field_errors:
            try:
                db.session.add(AdminUser(email=email, password_hash=generate_password_hash(password), role=role))
                audit('staff.created', f'{email}: {role}')
                db.session.commit()
                flash('Staff member created.', 'success')
                return redirect(url_for('admin.staff'))
            except IntegrityError:
                db.session.rollback()
                field_errors['email'] = 'Email: that staff email already exists.'
    page = db.paginate(db.select(AdminUser).order_by(AdminUser.email), per_page=10, error_out=False)
    return render_template('admin/staff.html', staff=page.items, page=page, field_errors=field_errors)

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
