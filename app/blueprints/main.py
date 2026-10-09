from pathlib import Path
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, abort, Response, current_app
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from ..extensions import db, limiter
from ..models import Audiobook, Author, Category, MediaAsset, ProductionEnquiry, NewsletterSubscriber, AnalyticsEvent
from ..services.access_service import normalize_email
from ..services.media_service import media_path

bp = Blueprint('main', __name__)

def visible_books():
    query = db.select(Audiobook).where(Audiobook.state == 'published')
    if not (current_app.config['DEMO_MODE'] or current_app.config['SAMPLE_CATALOG']):
        query = query.where(Audiobook.is_demo.is_(False))
    return query

@bp.get('/')
def home():
    books = db.session.scalars(visible_books().where(Audiobook.homepage_visible.is_(True)).order_by(Audiobook.published_at.desc(), Audiobook.id.desc()).limit(36)).all()
    home_query = visible_books().where(Audiobook.homepage_visible.is_(True))
    hero = db.session.scalar(home_query.where(Audiobook.hero.is_(True)).order_by(
        Audiobook.published_at.desc(), Audiobook.id.desc()).limit(1)) or (books[0] if books else None)
    shelf_books = [book for book in books if not hero or book.id != hero.id][:12]
    return render_template('home.html', hero=hero, shelf_books=shelf_books)

@bp.get('/books')
@bp.get('/genres/<genre_slug>', endpoint='category')
def catalog(genre_slug=None):
    if request.args.get('search') == 'all':
        return redirect(url_for('main.catalog', q=request.args.get('q', '').strip()[:150]))
    query = visible_books()
    q = request.args.get('q', '').strip()[:150]
    if q:
        escaped = q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        pattern = '%' + escaped + '%'
        query = query.join(Author).where(or_(Audiobook.title.ilike(pattern, escape='\\'),
            Author.name.ilike(pattern, escape='\\'), Audiobook.narrator.ilike(pattern, escape='\\'), Audiobook.synopsis.ilike(pattern, escape='\\')))
    category = genre_slug or request.args.get('genre', '')
    selected_genre = db.session.scalar(db.select(Category).where(Category.slug == category)) if category else None
    if genre_slug and not selected_genre:
        abort(404)
    if category:
        query = query.where(Audiobook.categories.any(Category.slug == category))
    for field in ['language', 'production_style', 'age_range']:
        if request.args.get(field):
            query = query.where(getattr(Audiobook, field) == request.args[field])
    if request.args.get('collection') == 'children':
        query = query.where(Audiobook.children.is_(True))
    if request.args.get('collection') == 'originals':
        query = query.where(Audiobook.original.is_(True))
    if request.args.get('duration') == 'short':
        query = query.where(Audiobook.duration_minutes <= 180)
    elif request.args.get('duration') == 'long':
        query = query.where(Audiobook.duration_minutes > 180)
    if request.args.get('price') == 'under20':
        query = query.where(Audiobook.currency == 'gbp', Audiobook.price_minor < 2000)
    sort = request.args.get('sort', 'newest')
    sorting = {'newest': Audiobook.published_at.desc(), 'featured': Audiobook.featured.desc(),
        'title': Audiobook.title.asc(), 'price': Audiobook.price_minor.asc()}
    page = db.paginate(query.order_by(sorting.get(sort, Audiobook.published_at.desc()), Audiobook.id), per_page=10, error_out=False)
    facets = db.session.scalars(visible_books()).all()
    return render_template('catalog.html', page=page, q=q, selected_genre=selected_genre,
        languages=sorted({b.language for b in facets}), ages=sorted({b.age_range for b in facets if b.age_range}))

@bp.get('/books/<slug>')
def book(slug):
    book = db.session.scalar(visible_books().where(Audiobook.slug == slug))
    if not book:
        abort(404)
    db.session.add(AnalyticsEvent(book_id=book.id, kind='book_view'))
    db.session.commit()
    related = db.session.scalars(visible_books().where(Audiobook.id != book.id,
        or_(Audiobook.author_id == book.author_id, Audiobook.categories.any(Category.id.in_([c.id for c in book.categories])))).limit(4)).all()
    schema = {'@context': 'https://schema.org', '@type': 'Book', 'name': book.title,
        'description': book.synopsis, 'author': {'@type': 'Person', 'name': book.author.name},
        'inLanguage': book.language, 'image': current_app.config['BASE_URL'] + book.cover_url,
        'url': current_app.config['BASE_URL'] + url_for('main.book', slug=book.slug),
        'offers': {'@type': 'Offer', 'price': f'{book.price_minor / 100:.2f}',
            'priceCurrency': book.currency.upper(), 'availability': 'https://schema.org/InStock'}}
    return render_template('book.html', book=book, related=related, book_schema=schema if not book.is_demo and book.saleable else None)

@bp.post('/books/<string:book_id>/trailer-play')
@limiter.limit('30 per minute')
def trailer_event(book_id):
    book = db.session.scalar(visible_books().where(Audiobook.id == book_id))
    if not book:
        abort(404)
    db.session.add(AnalyticsEvent(book_id=book.id, kind='trailer_play'))
    db.session.commit()
    return {'ok': True}

@bp.get('/media/public/<media_id>')
def public_media(media_id):
    asset = db.get_or_404(MediaAsset, media_id)
    if asset.kind not in {'cover', 'trailer', 'compare_plain', 'compare_immersive'}:
        abort(404)
    if asset.book.state != 'published' or (asset.book.is_demo and not (current_app.config['DEMO_MODE'] or current_app.config['SAMPLE_CATALOG'])):
        abort(404)
    path = media_path(asset)
    if not path.is_file():
        abort(404)
    return send_file(path, mimetype=asset.mime_type, conditional=True, max_age=3600)

@bp.get('/authors/<slug>')
def author(slug):
    author = db.session.scalar(db.select(Author).where(Author.slug == slug))
    if not author:
        abort(404)
    books = db.session.scalars(visible_books().where(Audiobook.author_id == author.id)).all()
    return render_template('author.html', author=author, books=books)

@bp.route('/production', methods=['GET', 'POST'])
@limiter.limit('10 per hour', methods=['POST'])
def production():
    if request.method == 'POST':
        try:
            email = normalize_email(request.form.get('email'))
            name = request.form.get('name', '').strip()[:150]
            title = request.form.get('title', '').strip()[:180]
            message = request.form.get('message', '').strip()[:10000]
            if not all([name, title, message]):
                raise ValueError('Complete all fields so we can understand your project.')
            if request.form.get('website'):
                return redirect(url_for('main.production'))
            from ..services.enquiry_service import project_details, save_manuscript
            if not request.form.get('consent'):
                raise ValueError('Please agree to the use of your details for this enquiry.')
            details = project_details(request.form)
            attachment = save_manuscript(request.files.get('manuscript'))
            enquiry = ProductionEnquiry(name=name, email=email, title=title, message=message, project_details=details)
            if attachment: enquiry.attachment_key, enquiry.attachment_name = attachment
            db.session.add(enquiry)
            db.session.add(AnalyticsEvent(kind='author_enquiry'))
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                if attachment: (Path(current_app.config['MEDIA_ROOT']) / attachment[0]).unlink(missing_ok=True)
                raise
            flash('Your project is on our desk. The production team will review your enquiry.', 'success')
            return redirect(url_for('main.production'))
        except ValueError as error:
            flash(str(error), 'error')
    return render_template('production.html')

@bp.post('/newsletter')
@limiter.limit('10 per hour')
def newsletter():
    try:
        email = normalize_email(request.form.get('email'))
        if not request.form.get('consent'):
            raise ValueError('Please agree to receive shelf updates.')
        if not db.session.scalar(db.select(NewsletterSubscriber).where(NewsletterSubscriber.email == email)):
            db.session.add(NewsletterSubscriber(email=email, first_name=request.form.get('first_name', '').strip()[:100]))
            db.session.commit()
        flash('You’re on the list. Welcome to the Shelf.', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('You’re on the list. Welcome to the Shelf.', 'success')
    except ValueError as error:
        flash(str(error), 'error')
    return redirect(url_for('main.home') + '#newsletter')

@bp.get('/sitemap.xml')
def sitemap():
    from ..content.company import PAGES
    pages = [current_app.config['BASE_URL'] + '/' + slug for slug in PAGES] + [current_app.config['BASE_URL'] + url_for('main.contact'), current_app.config['BASE_URL'] + url_for('main.home'), current_app.config['BASE_URL'] + url_for('main.catalog'), current_app.config['BASE_URL'] + url_for('main.production')]
    books = db.session.scalars(visible_books().where(Audiobook.is_demo.is_(False))).all()
    pages.extend(current_app.config['BASE_URL'] + url_for('main.book', slug=b.slug) for b in books)
    authors = db.session.scalars(db.select(Author).where(Author.id.in_({b.author_id for b in books}))).all()
    categories = db.session.scalars(db.select(Category).where(Category.id.in_({c.id for b in books for c in b.categories}))).all()
    pages.extend(current_app.config['BASE_URL'] + url_for('main.category', genre_slug=c.slug) for c in categories)
    pages.extend(current_app.config['BASE_URL'] + url_for('main.author', slug=a.slug) for a in authors)
    return Response(render_template('sitemap.xml', pages=pages), mimetype='application/xml')

@bp.get('/robots.txt')
def robots():
    return Response('User-agent: *\nDisallow: /admin\nDisallow: /library\nDisallow: /checkout\nDisallow: /cart\nSitemap: ' + current_app.config['BASE_URL'] + '/sitemap.xml\n', mimetype='text/plain')

@bp.get('/health')
def health():
    db.session.execute(db.text('SELECT 1'))
    return {'status': 'ok'}


@bp.get('/about')
@bp.get('/services')
@bp.get('/immersive-audio')
@bp.get('/children')
@bp.get('/originals')
@bp.get('/innovation')
@bp.get('/privacy')
@bp.get('/terms')
@bp.get('/accessibility')
def company():
    from ..content.company import PAGES
    slug = request.path.strip('/')
    books = []
    if slug in {'children','originals'}:
        flag = Audiobook.children if slug == 'children' else Audiobook.original
        books = db.session.scalars(visible_books().where(flag.is_(True)).limit(4)).all()
    comparison = next((b for b in db.session.scalars(visible_books()).all() if b.asset('compare_plain') and b.asset('compare_immersive')), None) if slug == 'immersive-audio' else None
    return render_template('company.html', content=PAGES[slug], slug=slug, collection_books=books, comparison=comparison)

@bp.route('/contact', methods=['GET','POST'])
@limiter.limit('10 per hour', methods=['POST'])
def contact():
    from ..services.enquiry_service import ENQUIRY_TYPES
    if request.method == 'POST':
        try:
            if request.form.get('website'):return redirect(url_for('main.contact'))
            email=normalize_email(request.form.get('email'))
            name=request.form.get('name','').strip()[:150]
            message=request.form.get('message','').strip()[:10000]
            kind=request.form.get('enquiry_type','general')
            if not name or not message or kind not in ENQUIRY_TYPES:raise ValueError('Complete your name, enquiry type and message.')
            if not request.form.get('consent'):raise ValueError('Please agree to the use of your details for this enquiry.')
            db.session.add(ProductionEnquiry(name=name,email=email,title=ENQUIRY_TYPES[kind],message=message,enquiry_type=kind))
            db.session.add(AnalyticsEvent(kind='contact_submission'))
            db.session.commit()
            flash('Your enquiry has been received. Our team will review your message.', 'success')
            return redirect(url_for('main.contact'))
        except ValueError as error:flash(str(error),'error')
    return render_template('contact.html', enquiry_types=ENQUIRY_TYPES)


@bp.post('/engagement')
@limiter.limit('30 per minute')
def engagement():
    data=request.get_json(silent=True) or {}
    if data.get('kind') not in {'audio_start','audio_complete'}:abort(400)
    db.session.add(AnalyticsEvent(kind=data['kind']))
    db.session.commit()
    return {'recorded':True}
