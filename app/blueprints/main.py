import json
from pathlib import Path
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, abort, Response, current_app, after_this_request
from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from ..extensions import db, limiter
from ..models import Audiobook, Author, Category, MediaAsset, ProductionEnquiry, NewsletterSubscriber, AnalyticsEvent
from .. import seo
from ..services.access_service import normalize_email
from ..services.media_service import media_path, cover_variant
from ..services.analytics_service import record_after_response

bp = Blueprint('main', __name__)
COVER_WIDTHS = {360, 720}

def published_books():
    query = db.select(Audiobook).where(Audiobook.state == 'published')
    if not (current_app.config['DEMO_MODE'] or current_app.config['SAMPLE_CATALOG']):
        query = query.where(Audiobook.is_demo.is_(False))
    return query

def visible_books():
    # Load a shelf's authors, genres and media in one query apiece rather than one query per book.
    return published_books().options(selectinload(Audiobook.author), selectinload(Audiobook.categories), selectinload(Audiobook.media))

def shelf_genres():
    # Genres with at least one book on the shelf, so visitors are never sent to an empty page.
    used = published_books().join(Audiobook.categories).with_only_columns(Category.id)
    return db.session.scalars(db.select(Category).where(Category.id.in_(used)).order_by(Category.position, Category.name)).all()

@bp.get('/')
def home():
    import random
    from itertools import chain, zip_longest
    books = db.session.scalars(visible_books().where(Audiobook.homepage_visible.is_(True))).all()
    random.shuffle(books)
    # A fresh mix on every visit: take turns across genres so no single genre fills the shelf.
    by_genre = {}
    for book in books:
        by_genre.setdefault(book.categories[0].slug if book.categories else '', []).append(book)
    groups = list(by_genre.values())
    random.shuffle(groups)
    shelf_books = [b for b in chain.from_iterable(zip_longest(*groups)) if b][:12]
    from ..content.legal import COMPANY
    return render_template('home.html', shelf_books=shelf_books, company=COMPANY)

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
    if page.page > 1 and not page.items:
        abort(404)
    facets = db.session.execute(published_books().with_only_columns(Audiobook.language, Audiobook.age_range)).all()
    canonical, noindex = seo.listing_state(request.args, genre_slug, selected_genre, page)
    trail = [('Home', '/'), ('Audiobooks', url_for('main.catalog'))] + ([(selected_genre.name, url_for('main.category', genre_slug=selected_genre.slug))] if genre_slug else [])
    return render_template('catalog.html', page=page, q=q, selected_genre=selected_genre, canonical=canonical, noindex=noindex,
        schema=None if noindex else seo.graph(seo.breadcrumbs(*trail)),
        languages=sorted({b.language for b in facets}), ages=sorted({b.age_range for b in facets if b.age_range}))

@bp.get('/featured')
def featured():
    # Only unpriced featured titles: once a price is added the book lives on the bookshelf.
    coming_soon = db.session.scalars(visible_books().where(Audiobook.featured.is_(True), Audiobook.price_minor <= 0)
        .order_by(Audiobook.published_at.desc(), Audiobook.id.desc()).limit(48)).all()
    return render_template('featured.html', coming_soon=coming_soon)

@bp.get('/books/<slug>')
def book(slug):
    book = db.session.scalar(visible_books().where(Audiobook.slug == slug))
    if not book:
        abort(404)
    after_this_request(lambda response: record_after_response(response, book_id=book.id, kind='book_view'))
    related = db.session.scalars(visible_books().where(Audiobook.id != book.id,
        or_(Audiobook.author_id == book.author_id, Audiobook.categories.any(Category.id.in_([c.id for c in book.categories])))).limit(4)).all()
    trail = [('Home', '/'), ('Audiobooks', url_for('main.catalog'))]
    if book.categories:
        trail.append((book.categories[0].name, url_for('main.category', genre_slug=book.categories[0].slug)))
    trail.append((book.title, url_for('main.book', slug=book.slug)))
    from ..content.legal import RECORDING_NOTICE_AUTHORS
    return render_template('book.html', book=book, related=related, trail=trail, noindex=not book.indexable, description=seo.book_description(book),
        schema=None if book.is_demo else seo.graph(seo.book_schema(book), seo.breadcrumbs(*trail)),
        recording_notice=book.author.slug in RECORDING_NOTICE_AUTHORS)

@bp.post('/books/<string:book_id>/trailer-play')
@limiter.limit('30 per minute')
def trailer_event(book_id):
    book = db.session.scalar(published_books().where(Audiobook.id == book_id))
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
    width = request.args.get('w', type=int)
    if width is not None:
        # Page-sized WebP covers. A new upload gets a new media id, so the copy can be cached for a month.
        if asset.kind != 'cover' or width not in COVER_WIDTHS:
            abort(404)
        return send_file(cover_variant(path, width), mimetype='image/webp', conditional=True, max_age=30 * 24 * 3600)
    return send_file(path, mimetype=asset.mime_type, conditional=True, max_age=3600)

@bp.get('/authors/<slug>')
def author(slug):
    author = db.session.scalar(db.select(Author).where(Author.slug == slug))
    books = db.session.scalars(visible_books().where(Audiobook.author_id == author.id)
        .order_by(Audiobook.published_at.desc(), Audiobook.id)).all() if author else []
    # An author with nothing on the shelf, such as an old sample profile, has no page.
    if not books:
        abort(404)
    available = [b for b in books if not b.coming_soon]
    coming = [b for b in books if b.coming_soon]
    genres = list({c.slug: c for b in books for c in b.categories}.values())
    narrated = sum(1 for b in books if b.narrator == author.name)
    names = [b.title for b in (available or coming)[:3]]
    listing = ', '.join(names[:-1]) + ' and ' + names[-1] if len(names) > 1 else names[0]
    description = seo.summary(author.bio) if author.bio else seo.summary(f'Audiobooks by {author.name} on MyAudioShelf, including {listing}.'
        + (f' {len(coming)} more coming soon.' if coming and available else '') + ' Play free previews and listen online.')
    trail = [('Home', '/'), ('Audiobooks', url_for('main.catalog')), (author.name, url_for('main.author', slug=author.slug))]
    url = seo.absolute(url_for('main.author', slug=author.slug))
    person = {'@type': 'Person', '@id': url + '#person', 'name': author.name, 'url': url, **({'description': author.bio} if author.bio else {})}
    schema = seo.graph({'@type': 'ProfilePage', '@id': url, 'url': url, 'name': f'{author.name} audiobooks', 'mainEntity': person}, seo.breadcrumbs(*trail))
    return render_template('author.html', author=author, available=available, coming=coming, genres=genres, narrated=narrated,
        description=description, trail=trail, schema=schema)

def recent_productions(limit=4):
    # Audiobooks MyAudioShelf recorded and has on sale: real examples of the production work.
    from ..content.legal import RECORDING_NOTICE_AUTHORS
    return db.session.scalars(visible_books().where(Audiobook.saleable.is_(True), Audiobook.price_minor > 0,
        Audiobook.author.has(Author.slug.in_(RECORDING_NOTICE_AUTHORS))).order_by(Audiobook.published_at.desc(), Audiobook.id).limit(limit)).all()

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
            flash('generate_lead', 'analytics')
            return redirect(url_for('main.production'))
        except ValueError as error:
            flash(str(error), 'error')
    trail = [('Home', '/'), ('Audiobook production', url_for('main.production'))]
    return render_template('production.html', productions=recent_productions(), trail=trail,
        schema=seo.graph(seo.breadcrumbs(*trail), service_schema('Audiobook production for authors and publishers', url_for('main.production'))))

def service_schema(name, path):
    return {'@type': 'Service', 'name': name, 'url': seo.absolute(path), 'provider': seo.organization_ref(), 'areaServed': 'Worldwide',
        'serviceType': ['Audiobook narration', 'Audiobook editing and mastering', 'Sound design', 'Dramatised audiobook production', 'Audiobook translation', 'Audiobook publishing']}

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
            flash('sign_up', 'analytics')
        flash('You’re on the list. Welcome to the Shelf.', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('You’re on the list. Welcome to the Shelf.', 'success')
    except ValueError as error:
        flash(str(error), 'error')
    return redirect(url_for('main.home') + '#newsletter')

@bp.get('/sitemap.xml')
def sitemap():
    # Every page meant to rank, and only those: no searches, filters, private areas or titles still waiting on a description.
    from ..content.company import PAGES
    from ..content.legal import DOCUMENTS
    from ..content.articles import ARTICLES
    page = lambda path, lastmod=None, image=None: {'loc': seo.absolute(path), 'lastmod': lastmod, 'image': image and seo.absolute(image)}
    books = db.session.scalars(visible_books().where(Audiobook.is_demo.is_(False)).order_by(Audiobook.title)).all()
    pages = [page(url_for('main.home')), page(url_for('main.catalog')), page(url_for('main.featured')), page(url_for('main.production')),
        *(page('/' + slug) for slug in PAGES), page(url_for('main.resources'), max(a['updated'] for a in ARTICLES.values())),
        *(page(url_for('main.article', slug=slug), article['updated']) for slug, article in ARTICLES.items()),
        page(url_for('main.contact')), *(page('/' + slug) for slug in DOCUMENTS)]
    pages += [page(url_for('main.book', slug=b.slug), image=b.cover_url) for b in books if b.indexable]
    pages += [page(url_for('main.category', genre_slug=c.slug)) for c in sorted({c.slug: c for b in books for c in b.categories}.values(), key=lambda c: (c.position, c.name))]
    pages += [page(url_for('main.author', slug=a.slug)) for a in sorted({b.author.slug: b.author for b in books}.values(), key=lambda a: a.name)]
    return Response(render_template('sitemap.xml', pages=pages), mimetype='application/xml')

@bp.get('/privacy')
@bp.get('/terms')
@bp.get('/cookies')
@bp.get('/copyright')
def legal():
    from ..content.legal import DOCUMENTS, COMPANY, EFFECTIVE, ANALYTICS_COOKIES
    slug = request.path.strip('/')
    doc = DOCUMENTS[slug]
    if slug == 'cookies' and current_app.config['GA_MEASUREMENT_ID']:
        # With Google Analytics switched on, the policy describes its cookies instead of saying there are none.
        doc = dict(doc, document=[ANALYTICS_COOKIES if heading == ANALYTICS_COOKIES[0] else (heading, blocks) for heading, blocks in doc['document']])
    return render_template('legal.html', doc=doc, slug=slug, documents=DOCUMENTS, company=COMPANY, effective=EFFECTIVE)

@bp.get('/robots.txt')
def robots():
    # Staff, cart and account pages stay crawlable so search engines can read their noindex header;
    # a blocked page that other pages link to can still be listed by its address alone.
    rules = ['User-agent: *', 'Allow: /', 'Disallow: /checkout/', 'Disallow: /library/', 'Disallow: /media/private/', 'Disallow: /cart/',
        '', 'Sitemap: ' + seo.absolute('/sitemap.xml')]
    return Response('\n'.join(rules) + '\n', mimetype='text/plain')

@bp.get('/merchant-feed.xml')
def merchant_feed():
    # Google Merchant Center fetches this daily to list audiobooks in Google Shopping.
    # Only titles checkout will sell: priced in pounds, with a cover and chapter or full-book audio.
    books = db.session.scalars(visible_books().options(selectinload(Audiobook.chapters))
        .where(Audiobook.saleable.is_(True), Audiobook.price_minor > 0, Audiobook.currency == 'gbp', Audiobook.is_demo.is_(False))
        .order_by(Audiobook.title)).all()
    books = [b for b in books if b.asset('cover') and (b.chapters or b.asset('full'))]
    response = Response(render_template('merchant_feed.xml', books=books), mimetype='application/xml')
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response

@bp.get('/manifest.webmanifest')
def web_manifest():
    # Lets visitors install the shop as an app on phones, tablets and computers.
    icon = lambda name, size, purpose='any': {'src': url_for('static', filename='icons/' + name), 'sizes': size, 'type': 'image/png', 'purpose': purpose}
    shot = lambda name, size, form, label: {'src': url_for('static', filename='images/app/' + name), 'sizes': size, 'type': 'image/webp', 'form_factor': form, 'label': label}
    shortcut = lambda name, path: {'name': name, 'url': path, 'icons': [icon('shortcut-96.png', '96x96')]}
    manifest = {'id': '/', 'name': 'MyAudioShelf', 'short_name': 'MyAudioShelf', 'lang': 'en-GB', 'dir': 'ltr',
        'description': 'Immersive audiobooks, dramatised productions and children’s audio. Listen a little. Discover a lot.',
        'start_url': '/', 'scope': '/', 'display': 'standalone', 'background_color': '#111813', 'theme_color': '#111813',
        'categories': ['books', 'entertainment', 'education'], 'prefer_related_applications': False,
        'icons': [icon('app-192.png', '192x192'), icon('app-512.png', '512x512'),
            icon('app-maskable-192.png', '192x192', 'maskable'), icon('app-maskable-512.png', '512x512', 'maskable')],
        'screenshots': [shot('home-wide.webp', '1440x900', 'wide', 'Stories worth listening to'),
            shot('bookshelf-wide.webp', '1440x900', 'wide', 'The bookshelf'),
            shot('home-narrow.webp', '780x1688', 'narrow', 'Stories worth listening to'),
            shot('bookshelf-narrow.webp', '780x1688', 'narrow', 'The bookshelf'),
            shot('featured-narrow.webp', '780x1688', 'narrow', 'Featured and coming soon')],
        'shortcuts': [shortcut('Browse audiobooks', '/books'), shortcut('Featured & coming soon', '/featured'), shortcut('My purchases', '/library')]}
    response = Response(json.dumps(manifest, ensure_ascii=False), mimetype='application/manifest+json')
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response

@bp.get('/sw.js')
def service_worker():
    # Served from the root so it covers every page; no-cache lets updates arrive on the next visit.
    response = send_file(Path(current_app.static_folder) / 'js' / 'sw.js', mimetype='text/javascript')
    response.headers['Cache-Control'] = 'no-cache'
    return response

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
@bp.get('/accessibility')
def company():
    from ..content.company import PAGES, DETAILS
    slug = request.path.strip('/')
    books = []
    if slug in {'children','originals'}:
        flag = Audiobook.children if slug == 'children' else Audiobook.original
        books = db.session.scalars(visible_books().where(flag.is_(True)).limit(4)).all()
    comparison = next((b for b in db.session.scalars(visible_books()).all() if b.asset('compare_plain') and b.asset('compare_immersive')), None) if slug == 'immersive-audio' else None
    content = PAGES[slug]
    trail = [('Home', '/'), (content['title'], '/' + slug)]
    service = service_schema('Audiobook and audio production services', '/services') if slug == 'services' else None
    return render_template('company.html', content=content, details=DETAILS.get(slug), slug=slug, collection_books=books, comparison=comparison, trail=trail,
        productions=recent_productions() if slug in {'services', 'immersive-audio'} else [], schema=seo.graph(seo.breadcrumbs(*trail), service))

@bp.get('/resources')
def resources():
    from ..content.articles import ARTICLES
    trail = [('Home', '/'), ('Guides & resources', url_for('main.resources'))]
    return render_template('resources.html', articles=ARTICLES, trail=trail, schema=seo.graph(seo.breadcrumbs(*trail)))

@bp.get('/resources/<slug>')
def article(slug):
    from ..content.articles import ARTICLES
    article = ARTICLES.get(slug) or abort(404)
    trail = [('Home', '/'), ('Guides & resources', url_for('main.resources')), (article['title'], url_for('main.article', slug=slug))]
    url = seo.absolute(url_for('main.article', slug=slug))
    schema = seo.graph({'@type': 'Article', '@id': url + '#article', 'headline': article['title'], 'description': article['summary'], 'url': url,
        'mainEntityOfPage': url, 'datePublished': article['published'], 'dateModified': article['updated'], 'inLanguage': 'en-GB',
        'image': seo.absolute(url_for('static', filename='images/app/share.jpg')), 'author': seo.organization_ref(), 'publisher': seo.organization_ref()},
        seo.breadcrumbs(*trail))
    more = [(key, other) for key, other in ARTICLES.items() if key != slug][:3]
    return render_template('article.html', article=article, slug=slug, more=more, trail=trail, schema=schema)

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
            flash('generate_lead', 'analytics')
            return redirect(url_for('main.contact'))
        except ValueError as error:flash(str(error),'error')
    return render_template('contact.html', enquiry_types=ENQUIRY_TYPES)


@bp.post('/engagement')
@limiter.limit('30 per minute')
def engagement():
    data=request.get_json(silent=True) or {}
    if data.get('kind') not in {'audio_start','audio_complete','app_install'}:abort(400)
    db.session.add(AnalyticsEvent(kind=data['kind']))
    db.session.commit()
    return {'recorded':True}
