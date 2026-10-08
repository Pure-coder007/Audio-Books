"""Import the two supplied audiobook folders, including credits and cover art."""
import argparse
import math
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mutagen import File as AudioFile
from PIL import Image
from app import create_app
from app.extensions import db
from app.models import Audiobook, Author, Category, Chapter, MediaAsset, AuditLog, now
from app.services.storage_service import upload, enabled

BOOKS = [
    dict(folder='1000 WORDS OF WISDOM', title='1000 Words of Wisdom', slug='1000-words-of-wisdom',
         cover='1000 words of wisdom.jpeg', genre='Wisdom & Inspiration',
         synopsis='1000 Words of Wisdom by David Mozie. Listen to the complete audiobook, including opening and closing credits.',
         tracks=[('Opening Credits', 'BEGINING CREDIT 192.mp3'),
                 ('1000 Words of Wisdom', '1000 Words of Wisdom by David Mozie 192.mp3'),
                 ('Closing Credits', 'ENDING CREDIT..192.mp3')], preview_index=1),
    dict(folder='AUTHORS GAMBLE', title='Authors Gamble', slug='authors-gamble',
         cover='Authors Gamble.jpeg', genre='Writing & Publishing',
         synopsis='Authors Gamble: Ink & Risk by David Mozie. Eight chapters about writing, with opening credits, a conclusion and closing credits.',
         tracks=[('Opening Credits', 'OPENING CREDIT.mp3')] +
                [(f'Chapter {i}', f'CHAPTER {i}.mp3') for i in range(1, 9)] +
                [('Conclusion', 'CONCLUSION.mp3'), ('Closing Credits', 'CLOSING CREDIT.mp3')], preview_index=1),
]


def prepare(root, media_root):
    prepared = []
    media_root.mkdir(parents=True, exist_ok=True)
    for spec in BOOKS:
        folder = root / spec['folder']
        assets = []
        with Image.open(folder / spec['cover']) as image:
            image.load()
            cover = media_root / (spec['slug'] + '-cover.jpg')
            image.thumbnail((1600, 2400))
            image.convert('RGB').save(cover, quality=90)
        assets.append(dict(kind='cover', path=cover, duration=0, mime='image/jpeg'))
        for position, (title, filename) in enumerate(spec['tracks'], 1):
            source = folder / filename
            audio = AudioFile(source)
            if audio is None or audio.info.length <= 0:
                raise ValueError(f'Invalid audio: {source}')
            target = media_root / f"{spec['slug']}-{position:03d}.mp3"
            shutil.copyfile(source, target)
            assets.append(dict(kind='chapter', title=title, position=position,
                               path=target, duration=audio.info.length, mime='audio/mpeg'))
        trailer = media_root / (spec['slug'] + '-preview.mp3')
        source = folder / spec['tracks'][spec['preview_index']][1]
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                        '-i', str(source), '-t', '45', '-vn', '-codec:a', 'libmp3lame',
                        '-b:a', '128k', str(trailer)], check=True)
        assets.append(dict(kind='trailer', path=trailer, duration=AudioFile(trailer).info.length,
                           mime='audio/mpeg'))
        prepared.append((spec, assets))
        print(f"Prepared {spec['title']}: {len(spec['tracks'])} tracks, cover and 45-second preview.", flush=True)
    return prepared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--price', type=int, default=1499, help='Price in pence (default: 1499)')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if args.price <= 0:
        parser.error('Price must be positive.')
    app = create_app()
    prepared = prepare(Path(app.root_path).parent / 'docs' / 'Books to add', Path(app.config['MEDIA_ROOT']))
    if args.prepare_only:
        return
    with app.app_context():
        if not enabled():
            raise RuntimeError('Configure private Bunny Storage before importing into the live catalog.')
        # Finish all remote uploads before publishing any catalog records.
        for spec, assets in prepared:
            for asset in assets:
                upload(asset['path'].name)
                print(f"Uploaded {spec['title']}: {asset['path'].name}", flush=True)
        author = db.session.scalar(db.select(Author).where(Author.slug == 'david-mozie'))
        if not author:
            author = Author(name='David Mozie', slug='david-mozie')
            db.session.add(author)
        for spec, assets in prepared:
            book = db.session.scalar(db.select(Audiobook).where(Audiobook.slug == spec['slug']))
            if book:
                print(f"Already imported: {book.title}; existing metadata preserved.", flush=True)
                continue
            category = db.session.scalar(db.select(Category).where(Category.name == spec['genre']))
            if not category:
                category = Category(name=spec['genre'], slug=spec['genre'].lower().replace(' & ', '-').replace(' ', '-'), position=9)
                db.session.add(category)
            seconds = sum(a['duration'] for a in assets if a['kind'] == 'chapter')
            book = Audiobook(title=spec['title'], slug=spec['slug'], author=author,
                             synopsis=spec['synopsis'], language='English', production_style='Narrated',
                             duration_minutes=math.ceil(seconds / 60), price_minor=args.price, currency='gbp',
                             state='published', saleable=True, homepage_visible=True, featured=True,
                             is_demo=False, published_at=now(), categories=[category])
            db.session.add(book)
            for item in assets:
                asset = MediaAsset(book=book, kind=item['kind'], storage_key=item['path'].name,
                                   mime_type=item['mime'], size_bytes=item['path'].stat().st_size,
                                   duration_seconds=item['duration'])
                db.session.add(asset)
                if item['kind'] == 'chapter':
                    book.chapters.append(Chapter(title=item['title'], position=item['position'], media=asset))
            db.session.add(AuditLog(action='book.imported', detail=f"Imported {book.title} from supplied folder with cover, ordered tracks and preview; price GBP {args.price / 100:.2f}."))
        db.session.commit()
        for spec, _ in prepared:
            book = db.session.scalar(db.select(Audiobook).where(Audiobook.slug == spec['slug']))
            assert book.asset('cover') and book.asset('trailer') and len(book.chapters) == len(spec['tracks'])
            print(f"Published {book.title}: {book.duration_label}, {len(book.chapters)} tracks, GBP {book.price_minor / 100:.2f}", flush=True)


if __name__ == '__main__':
    main()
