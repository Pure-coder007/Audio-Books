import io
from pathlib import Path
from uuid import uuid4
from flask import current_app
from PIL import Image, UnidentifiedImageError
from mutagen import File as AudioFile
import wave
from ..extensions import db
from ..models import MediaAsset

AUDIO_TYPES = {'.mp3': 'audio/mpeg', '.mpeg': 'audio/mpeg', '.mpga': 'audio/mpeg', '.mp2': 'audio/mpeg', '.m4a': 'audio/mp4', '.m4b': 'audio/mp4',
    '.aac': 'audio/aac', '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.flac': 'audio/flac'}
AUDIO_ACCEPT = ','.join(AUDIO_TYPES)
MPEG_MIMES = {'audio/mpeg', 'audio/mp3', 'audio/mpg', 'audio/x-mpeg', 'audio/mp2'}

def media_path(asset):
    from .storage_service import path_for
    return path_for(asset.storage_key)

def store_upload(upload, book, kind):
    suffix = Path(upload.filename or '').suffix.lower()
    key = uuid4().hex
    data = upload.read()
    if not data:
        raise ValueError('Uploaded file is empty.')
    if kind == 'cover':
        if suffix not in {'.jpg', '.jpeg', '.png', '.webp'} or len(data) > 10 * 1024 * 1024:
            raise ValueError('Cover must be a JPG, PNG or WebP up to 10 MB.')
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.width * image.height > 16_000_000:
                    raise ValueError('Cover image has too many pixels (maximum 16 megapixels).')
                image.load()
                if image.width < 200 or image.height < 200:
                    raise ValueError('Cover must be at least 200 × 200 pixels.')
                image.thumbnail((1600, 2400))
                clean = io.BytesIO()
                image.convert('RGB').save(clean, format='JPEG', quality=90)
                data = clean.getvalue()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise ValueError('Cover could not be decoded.') from error
        suffix, mime, duration = '.jpg', 'image/jpeg', 0
    else:
        if suffix not in AUDIO_TYPES or len(data) > 500 * 1024 * 1024:
            raise ValueError('Audio must be MP3, MPEG, M4A, M4B, AAC, WAV, OGG or FLAC up to 500 MB.')
        try:
            if suffix == '.wav':
                with wave.open(io.BytesIO(data)) as audio:
                    duration = audio.getnframes() / audio.getframerate()
            else:
                if suffix in {'.mp3', '.mpeg', '.mpga', '.mp2'}:
                    # Untagged MPEG audio is only recognised by name, so read it as MPEG directly.
                    from mutagen.mp3 import MP3
                    audio = MP3(io.BytesIO(data))
                else:
                    audio = AudioFile(io.BytesIO(data))
                mp4 = {'audio/mp4', 'audio/x-m4a'}
                accepted_mimes = {'.mp3': MPEG_MIMES, '.mpeg': MPEG_MIMES, '.mpga': MPEG_MIMES, '.mp2': MPEG_MIMES, '.m4a': mp4, '.m4b': mp4, '.aac': {'audio/x-aac', 'audio/aac'}, '.ogg': {'audio/ogg', 'audio/vorbis', 'audio/opus', 'audio/speex', 'audio/x-ogg'}, '.flac': {'audio/flac', 'audio/x-flac'}}
                if audio is None or not set(audio.mime).intersection(accepted_mimes[suffix]):
                    raise ValueError('Audio contents do not match the file extension.')
                duration = audio.info.length
            if duration <= 0:
                raise ValueError('Audio has no playable duration.')
        except Exception as error:
            raise ValueError('Audio could not be decoded; check its format.') from error
        if kind in {'trailer', 'compare_plain', 'compare_immersive'} and duration > 60.05:
            raise ValueError('A public trailer must be no longer than 60 seconds.')
        mime = AUDIO_TYPES[suffix]
    root = Path(current_app.config['MEDIA_ROOT'])
    root.mkdir(parents=True, exist_ok=True)
    storage_key = key + suffix
    (root / storage_key).write_bytes(data)
    from .storage_service import upload as upload_remote
    upload_remote(storage_key)
    asset = MediaAsset(book=book, kind=kind, storage_key=storage_key, mime_type=mime,
        size_bytes=len(data), duration_seconds=duration)
    db.session.add(asset)
    return asset

def publication_field_errors(book):
    errors = {}
    for field in ['title', 'synopsis', 'language']:
        if not getattr(book, field):
            errors[field] = f'{field.capitalize()} is required.'
    if not book.categories:
        errors['categories'] = 'Choose at least one genre.'
    if not book.asset('cover'):
        errors['cover'] = 'Upload a cover.'
    # Coming-soon titles are announced, not sold, so their recordings can follow later.
    if not book.coming_soon:
        if not book.asset('trailer'):
            errors['trailer'] = 'Upload a preview of up to 60 seconds.'
        if not book.asset('full') and not book.chapters:
            errors['full'] = 'Upload full audio or at least one chapter.'
    if book.price_minor <= 0 and not book.featured:
        errors['price'] = 'Set a price greater than zero in pounds, or tick Featured to publish it as Coming soon.'
    if book.is_demo:
        errors['state'] = 'Demo titles cannot be published for real sales; create your own title.'
    return errors


def publication_errors(book):
    return list(publication_field_errors(book).values())
