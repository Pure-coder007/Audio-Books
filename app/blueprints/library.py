import math
from flask import Blueprint, render_template, request, session, redirect, url_for, flash, abort, send_file, current_app
from ..extensions import db, limiter
from ..models import PurchaseEntitlement, Audiobook, MediaAsset, ListeningProgress, AnalyticsEvent
from ..services.access_service import normalize_email, consume_magic_link, has_access, media_token, verify_media_token
from ..services.email_service import queue_access_email, deliver_safely
from ..services.media_service import media_path

bp = Blueprint('library', __name__)

@bp.route('/library', methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
def index():
    if request.method == 'POST':
        try:
            email = normalize_email(request.form.get('email'))
            # Same response regardless of purchase state to avoid email enumeration.
            if db.session.scalar(db.select(PurchaseEntitlement.id).where(PurchaseEntitlement.email == email, PurchaseEntitlement.active.is_(True))):
                message = queue_access_email(email)
                db.session.commit()
                deliver_safely(message.id)
            flash('If this email has purchases, a listening link will arrive shortly. It expires in 15 minutes.', 'success')
            return redirect(url_for('library.index'))
        except ValueError as error:
            flash(str(error), 'error')
    email = session.get('listener_email')
    entitlements = db.session.scalars(db.select(PurchaseEntitlement).where(PurchaseEntitlement.email == email,
        PurchaseEntitlement.active.is_(True))).all() if email else []
    return render_template('library.html', entitlements=entitlements, email=email)

@bp.get('/library/access/<token>')
@limiter.limit('30 per minute')
def verify(token):
    # GET does not consume a token: email security scanners can safely follow it.
    return render_template('access.html', token=token, download_id=request.args.get('download', ''))

@bp.post('/library/access/<token>')
@limiter.limit('30 per minute')
def redeem(token):
    from ..services.identity_service import resolve_id
    download_id = resolve_id('audiobook', request.form.get('download')) if request.form.get('download') else None
    email = consume_magic_link(token)
    if not email:
        if download_id and has_access(session.get('listener_email'), download_id):
            return redirect(url_for('library.download', book_id=download_id))
        flash('That link has expired or was already used. Request a new one below.', 'error')
        return redirect(url_for('library.index'))
    cart = session.get('cart', [])
    session.clear()
    session['cart'] = cart
    session['listener_email'] = email
    session.permanent = True
    return redirect(url_for('library.download', book_id=download_id)) if download_id else redirect(url_for('library.index'))

@bp.post('/library/logout')
def logout():
    session.pop('listener_email', None)
    return redirect(url_for('library.index'))

@bp.get('/library/listen/<string:book_id>')
def listen(book_id):
    email = session.get('listener_email')
    if not has_access(email, book_id):
        abort(403)
    book = db.get_or_404(Audiobook, book_id)
    media = [c.media for c in book.chapters] if book.chapters else [book.asset('full')]
    media = [m for m in media if m]
    progress = db.session.scalar(db.select(ListeningProgress).where(ListeningProgress.email == email, ListeningProgress.book_id == book_id))
    tracks = [{'id': m.id, 'title': book.chapters[i].title if book.chapters else book.title,
        'url': url_for('library.stream', media_id=m.id, token=media_token(m.id, email))} for i, m in enumerate(media)]
    return render_template('listen.html', book=book, tracks=tracks, progress=progress)

@bp.get('/media/private/<media_id>')
def stream(media_id):
    email = verify_media_token(request.args.get('token', ''), media_id)
    asset = db.get_or_404(MediaAsset, media_id)
    if asset.kind not in {'full', 'chapter'} or not has_access(email, asset.book_id):
        abort(403)
    path = media_path(asset)
    if not path.is_file():
        abort(404)
    response = send_file(path, mimetype=asset.mime_type, conditional=True)
    response.headers['Cache-Control'] = 'private, no-store'
    return response

@bp.get('/library/media-url/<media_id>')
@limiter.limit('60 per minute')
def refresh_media(media_id):
    asset = db.get_or_404(MediaAsset, media_id)
    email = session.get('listener_email')
    if asset.kind not in {'full', 'chapter'} or not has_access(email, asset.book_id):
        abort(403)
    return {'url': url_for('library.stream', media_id=asset.id, token=media_token(asset.id, email))}

@bp.post('/library/progress/<string:book_id>')
@limiter.limit('30 per minute')
def save_progress(book_id):
    email = session.get('listener_email')
    if not has_access(email, book_id):
        abort(403)
    data = request.get_json(silent=True) or {}
    media = db.session.get(MediaAsset, data.get('media_id')) if isinstance(data.get('media_id'), str) else None
    try:
        seconds = float(data.get('seconds', 0))
    except (TypeError, ValueError):
        abort(400)
    if not media or media.book_id != book_id or media.kind not in {'chapter', 'full'} or not math.isfinite(seconds) or seconds < 0:
        abort(400)
    seconds = min(seconds, media.duration_seconds)
    progress = db.session.scalar(db.select(ListeningProgress).where(ListeningProgress.email == email, ListeningProgress.book_id == book_id))
    if not progress:
        progress = ListeningProgress(email=email, book_id=book_id)
        db.session.add(progress)
    progress.media_id, progress.seconds = media.id, seconds
    db.session.add(AnalyticsEvent(book_id=book_id, kind='listening_progress'))
    db.session.commit()
    return {'saved': True}

@bp.get('/library/download/<string:book_id>')
@limiter.limit('10 per hour')
def download(book_id):
    """A verified paid entitlement unlocks one file or every chapter in a ZIP."""
    from tempfile import TemporaryFile
    from zipfile import ZipFile, ZIP_STORED
    from pathlib import Path
    from werkzeug.utils import secure_filename
    from ..models import Order
    email = session.get('listener_email')
    paid = db.session.scalar(db.select(PurchaseEntitlement.id).join(Order,
        Order.id == PurchaseEntitlement.order_id).where(PurchaseEntitlement.email == email,
        PurchaseEntitlement.book_id == book_id, PurchaseEntitlement.active.is_(True), Order.status == 'paid')) if email else None
    if not paid: abort(403)
    book = db.get_or_404(Audiobook, book_id)
    assets = [chapter.media for chapter in book.chapters] if book.chapters else [book.asset('full')]
    if not assets or any(asset is None for asset in assets): abort(404)
    paths = [media_path(asset) for asset in assets]
    if any(not path.is_file() for path in paths):
        flash('The complete download is not available yet. Please contact our team for help with your purchase.', 'error')
        return redirect(url_for('library.index'))
    filename = secure_filename(book.slug) or f'audiobook-{book.id}'
    if not book.chapters:
        response = send_file(paths[0], mimetype=assets[0].mime_type, as_attachment=True,
            download_name=filename + paths[0].suffix, conditional=True)
    else:
        # A disk-backed temporary archive avoids holding the entire audiobook in RAM.
        archive = TemporaryFile(mode='w+b')
        try:
            with ZipFile(archive, 'w', compression=ZIP_STORED, allowZip64=True) as package:
                for index, (chapter, path) in enumerate(zip(book.chapters, paths), 1):
                    name = secure_filename(chapter.title)[:100] or 'Chapter'
                    package.write(path, f'{index:03d} - {name}{path.suffix}')
                cover = book.asset('cover')
                if cover and media_path(cover).is_file():
                    package.write(media_path(cover), 'Cover' + Path(cover.storage_key).suffix)
                package.writestr('Contents.txt', book.title + '\nBy ' + book.author.name + '\n\n' +
                    '\n'.join(f'{i:03d} - {c.title}' for i, c in enumerate(book.chapters, 1)))
            archive.seek(0)
            response = send_file(archive, mimetype='application/zip', as_attachment=True,
                download_name=filename + '.zip', conditional=False)
            response.call_on_close(archive.close)
        except Exception:
            archive.close()
            raise
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response
