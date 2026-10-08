"""Restore supplied public artwork/preview without publishing full recordings."""
from pathlib import Path
import shutil
from mutagen import File
from .extensions import db
from .models import Audiobook,Author,Category,MediaAsset,now

SLUG='5000-names-of-god'

def restore(app):
    # Preserve references from historical orders while removing samples from all shelves.
    db.session.execute(db.update(Audiobook).where(Audiobook.is_demo.is_(True)).values(state='archived',hero=False,featured=False,homepage_visible=False,saleable=False))
    author=db.session.scalar(db.select(Author).where(Author.slug=='david-mozie'))
    if not author:
        author=Author(name='David Mozie',slug='david-mozie');db.session.add(author)
    category=db.session.scalar(db.select(Category).where(Category.slug=='faith-and-spirituality'))
    if not category:
        category=Category(name='Faith & Spirituality',slug='faith-and-spirituality',position=8);db.session.add(category)
    book=db.session.scalar(db.select(Audiobook).where(Audiobook.slug==SLUG))
    if not book:
        book=Audiobook(slug=SLUG,title='5000 Names of God',author=author,categories=[category],synopsis='An audiobook by David Mozie exploring the names and attributes of God.',language='English',production_style='Immersive',state='published',saleable=False,featured=True,hero=True,homepage_visible=True,duration_minutes=208,price_minor=0,published_at=now())
        db.session.add(book)
    db.session.flush()
    source=Path(app.root_path)/'catalog_assets'/SLUG
    root=Path(app.config['MEDIA_ROOT']);root.mkdir(parents=True,exist_ok=True)
    for kind,filename,mime in [('cover','cover.jpeg','image/jpeg'),('trailer','preview.mp3','audio/mpeg')]:
        key=SLUG+'-'+filename
        shutil.copyfile(source/filename,root/key)
        if not book.asset(kind):
            duration=File(source/filename).info.length if kind=='trailer' else 0
            book.media.append(MediaAsset(kind=kind,storage_key=key,mime_type=mime,size_bytes=(source/filename).stat().st_size,duration_seconds=duration))
    db.session.commit()
    return book
