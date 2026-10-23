"""Import Victory Unattended, Deeds of Love and The Essence of Resilience from docs/Books to add."""
import argparse
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mutagen.mp3 import MP3
from PIL import Image
from app import create_app
from app.extensions import db
from app.models import Audiobook, Author, Category, Chapter, MediaAsset, AuditLog, now
from app.services.storage_service import upload, enabled

VICTORY = 'Victory unattended/WhatsApp Audio 2026-10-22 at '
BOOKS = [
    dict(slug='victory-unattended', title='Victory Unattended', price=1199, genre='Fiction',
         folder='Victory unattended', cover='5a753671-e801-4be3-a106-6e8a0cf7af53.jpeg',
         synopsis=None,  # keep the existing description
         tracks=[('Chapter 1: The Boy Who Saw a Lot', VICTORY + '5.03.55 AM (3).mpeg', []),
                 ('Chapter 2: Desire Creates Vision', VICTORY + '5.03.55 AM (4).mpeg', []),
                 ('Chapter 3: Talent Emerges', VICTORY + '5.03.55 AM (5).mpeg', []),
                 ('Chapter 4: The First Door Swings Open', VICTORY + '5.04.08 AM (3).mpeg', []),
                 # Two spoken notes from a writing tool were recorded by mistake; cut them out.
                 ('Chapter 6: The Great Opportunity', VICTORY + '5.04.08 AM (4).mpeg', 'CUTS_CH6'),
                 ('Chapter 7: Collapse Before Celebration', VICTORY + '5.04.08 AM (5).mpeg', [])],
         preview=(VICTORY + '5.03.55 AM (3).mpeg', 0, 45)),
    dict(slug='deeds-of-love', title='Deeds of Love', price=1099, genre='Wisdom & Inspiration',
         folder='Deeds of love', cover='image.png',
         synopsis='Deeds of Love by David Mozie is a gentle meditation on what love looks like in everyday life: '
                  'listening without rushing to reply, remembering what matters to someone, staying present, and choosing '
                  'kindness when it counts. A warm, reflective listen about the quiet acts that hold people together.',
         tracks=[('Deeds of Love', 'Deeds of love/WhatsApp Audio 2026-10-22 at 5.14.43 AM (2).mpeg', [])],
         preview=('Deeds of love/WhatsApp Audio 2026-10-22 at 5.14.43 AM (2).mpeg', 0, 45)),
    dict(slug='the-essence-of-resilience', title='The Essence of Resilience', price=999, genre='Wisdom & Inspiration',
         folder='Essence', cover='WhatsApp Image 2026-10-22 at 5.17.29 AM (1).jpeg',
         synopsis='The Essence of Resilience: A Poetic Journey by David Mozie. Poems about the courage to rise after every fall, '
                  'the strength to keep hoping, and the determination to continue when the path seems uncertain. '
                  'Resilience, these poems remind us, is not the absence of storms but the strength to grow through them.',
         tracks=[('The Essence of Resilience: A Poetic Journey', 'Essence/WhatsApp Audio 2026-10-22 at 5.19.22 AM (1).mpeg', []),
                 ('Closing', 'Essence/WhatsApp Audio 2026-10-22 at 5.19.13 AM (1).mpeg', [])],
         preview=('Essence/WhatsApp Audio 2026-10-22 at 5.19.23 AM (1).mpeg', 0, 60)),
]
CUTS = {'CUTS_CH6': []}  # filled in from the command line: start-end seconds


def encode(source, target, cuts=(), start=None, length=None):
    """Copy a recording as MP3, optionally removing time ranges or taking an excerpt."""
    command = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y']
    if start is not None:
        command += ['-ss', str(start), '-t', str(length)]
    command += ['-i', str(source), '-vn']
    if cuts:
        keep = ' + '.join(f'between(t,{a},{b})' for a, b in cuts)
        command += ['-af', f"aselect='not({keep})',asetpts=N/SR/TB"]
    command += ['-codec:a', 'libmp3lame', '-b:a', '192k', str(target)]
    subprocess.run(command, check=True)
    return MP3(target).info.length


def prepare(root, media_root):
    prepared = []
    for spec in BOOKS:
        assets = []
        with Image.open(root / spec['folder'] / spec['cover']) as image:
            image.load()
            cover = media_root / f"{spec['slug']}-cover-full.jpg"
            image.thumbnail((1600, 2400))
            image.convert('RGB').save(cover, quality=92)
        assets.append(dict(kind='cover', path=cover, duration=0, mime='image/jpeg'))
        for position, (title, filename, cuts) in enumerate(spec['tracks'], 1):
            target = media_root / f"{spec['slug']}-{position:03d}.mp3"
            duration = encode(root / filename, target, CUTS.get(cuts, cuts) if isinstance(cuts, str) else cuts)
            assets.append(dict(kind='chapter', title=title, position=position, path=target, duration=duration, mime='audio/mpeg'))
        source, start, length = spec['preview']
        trailer = media_root / f"{spec['slug']}-preview.mp3"
        assets.append(dict(kind='trailer', path=trailer, duration=encode(root / source, trailer, start=start, length=length), mime='audio/mpeg'))
        assert all(a['duration'] > 0 for a in assets if a['kind'] != 'cover') and assets[-1]['duration'] <= 60.05
        prepared.append((spec, assets))
        print(f"Prepared {spec['title']}: {len(spec['tracks'])} tracks, {sum(a['duration'] for a in assets if a['kind'] == 'chapter') / 60:.1f} min", flush=True)
    return prepared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cut-ch6', action='append', default=[], metavar='START-END', help='Seconds to remove from chapter 6')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    CUTS['CUTS_CH6'] = [tuple(float(x) for x in item.split('-')) for item in args.cut_ch6]
    app = create_app()
    media_root = Path(app.config['MEDIA_ROOT']); media_root.mkdir(parents=True, exist_ok=True)
    prepared = prepare(Path(app.root_path).parent / 'docs' / 'Books to add', media_root)
    if args.prepare_only:
        return
    with app.app_context():
        if not enabled():
            raise RuntimeError('Configure private Bunny Storage before importing into the live catalog.')
        for spec, assets in prepared:
            for asset in assets:
                upload(asset['path'].name)
            print(f"Uploaded {spec['title']} ({len(assets)} files)", flush=True)
        author = db.session.scalar(db.select(Author).where(Author.slug == 'david-mozie'))
        for spec, assets in prepared:
            category = db.session.scalar(db.select(Category).where(Category.name == spec['genre']))
            if not category:
                category = Category(name=spec['genre'], slug=spec['genre'].lower().replace(' & ', '-').replace(' ', '-'), position=9)
                db.session.add(category)
            book = db.session.scalar(db.select(Audiobook).where(Audiobook.slug == spec['slug']))
            if not book:
                book = Audiobook(title=spec['title'], slug=spec['slug'], author=author, language='English',
                                 production_style='Narrated', currency='gbp', categories=[category], published_at=now())
                db.session.add(book)
            elif book.chapters or book.asset('full'):
                print(f"{book.title} already has audio; left unchanged.", flush=True)
                continue
            for old in [m for m in book.media if m.kind in {'cover', 'trailer'}]:
                book.media.remove(old); db.session.delete(old)
            if spec['synopsis']:
                book.synopsis = spec['synopsis']
            book.price_minor, book.saleable, book.featured, book.state = spec['price'], True, False, 'published'
            book.homepage_visible, book.is_demo = True, False
            book.duration_minutes = math.ceil(sum(a['duration'] for a in assets if a['kind'] == 'chapter') / 60)
            for item in assets:
                asset = MediaAsset(book=book, kind=item['kind'], storage_key=item['path'].name, mime_type=item['mime'],
                                   size_bytes=item['path'].stat().st_size, duration_seconds=item['duration'])
                db.session.add(asset)
                if item['kind'] == 'chapter':
                    book.chapters.append(Chapter(title=item['title'], position=item['position'], media=asset))
            db.session.add(AuditLog(action='book.imported', detail=f"Imported {book.title}: {len(spec['tracks'])} tracks, preview, cover; GBP {spec['price'] / 100:.2f}"))
        db.session.commit()
        from app.services.media_service import publication_field_errors
        for spec, _ in prepared:
            book = db.session.scalar(db.select(Audiobook).where(Audiobook.slug == spec['slug']))
            assert not publication_field_errors(book), publication_field_errors(book)
            print(f"Published {book.title}: {book.duration_label}, {len(book.chapters)} tracks, GBP {book.price_minor / 100:.2f}", flush=True)


if __name__ == '__main__':
    main()
