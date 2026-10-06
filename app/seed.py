from datetime import timedelta
from pathlib import Path
import shutil
from .extensions import db
from .models import Author, Category, Audiobook, MediaAsset, now

TITLES = [
('the-last-train-to-lagos','The Last Train to Lagos','Ada Okonkwo','Tomi Adeyemi','Fiction','Immersive',510,650000,False,True),
('where-the-river-remembers','Where the River Remembers','Nneka Obi','Amara Eze','Fiction','Narrated',420,480000,False,False),
('the-art-of-starting-again','The Art of Starting Again','Dayo Bello','Femi Cole','Non-fiction','Narrated',245,550000,False,False),
('a-small-kind-of-magic','A Small Kind of Magic','Sade Akin','Bisola James','Children’s','Full cast',85,250000,True,True),
('letters-from-ibadan','Letters from Ibadan','Tunde Alabi','Wale Adebayo','Drama','Full cast',330,450000,False,True),
('when-we-were-rain','When We Were Rain','Imani Ade','Lara Williams','Romance','Narrated',390,500000,False,False),
('the-market-at-midnight','The Market at Midnight','Chidi Nwosu','Obi Daniel','Fiction','Immersive',470,620000,False,True),
('little-tortoise-big-world','Little Tortoise, Big World','Sade Akin','Bisola James','Children’s','Narrated',70,220000,True,False),
('a-pocketful-of-courage','A Pocketful of Courage','Dayo Bello','Femi Cole','Educational','Narrated',160,380000,False,False),
('home-is-a-sound','Home Is a Sound','Nneka Obi','Amara Eze','Drama','Immersive',310,420000,False,True),
('under-the-baobab','Under the Baobab','Chidi Nwosu','Obi Daniel','Fiction','Narrated',360,400000,False,False),
('the-moon-keeps-our-secrets','The Moon Keeps Our Secrets','Imani Ade','Lara Williams','Romance','Full cast',405,520000,False,False),
]

def seed(app):
    for i, name in enumerate(['Fiction','Non-fiction','Drama','Romance','Children’s','Educational','Originals','Horror']):
        slug = {'Non-fiction':'non-fiction','Children’s':'children'}.get(name, name.lower())
        if not db.session.scalar(db.select(Category).where(Category.slug == slug)):
            db.session.add(Category(name=name, slug=slug, position=i))
    db.session.flush()
    audio_root = Path(app.static_folder) / 'audio'
    private_root = Path(app.config['MEDIA_ROOT'])
    private_root.mkdir(parents=True, exist_ok=True)
    for i, (slug,title,author_name,narrator,genre,style,duration,price,children,original) in enumerate(TITLES):
        if db.session.scalar(db.select(Audiobook).where(Audiobook.slug == slug)):
            continue
        author_slug = author_name.lower().replace(' ', '-')
        author = db.session.scalar(db.select(Author).where(Author.slug == author_slug))
        if not author:
            author = Author(name=author_name, slug=author_slug, bio='A fictional author profile created to demonstrate the MyAudioShelf experience. Replace it with your own verified author biography.')
            db.session.add(author)
        category = db.session.scalar(db.select(Category).where(Category.name == genre))
        book = Audiobook(slug=slug, title=title, author=author, narrator=narrator, language='English',
            synopsis=f'An imagined story for the MyAudioShelf demo shelf. {title} invites listeners into a world of discovery, unexpected connections, and the moments that change us.\n\nThis title, author and narrator are fictional. The preview is a short demonstration narration, not a recording of a published book. Replace these samples with your own licensed productions before launch.',
            production_notes='Sample production metadata. Finished titles will describe their actual narration, cast and sound design.',
            credits='Demo content and original cover artwork created for the MyAudioShelf prototype.',
            transcript='Welcome to MyAudioShelf. This is a sample audio preview, created to demonstrate your listening experience. Imagine the first light of morning moving across the city. A train waits at the platform. Somewhere, a story is about to begin. Every great story starts with a voice. Find yours on the shelf.',
            production_style=style, duration_minutes=duration, price_minor=price, currency='ngn',
            state='published', featured=i < 4, hero=i == 0, original=original, children=children,
            age_range='4–8' if children else '', is_demo=True, published_at=now()-timedelta(days=i*3), categories=[category])
        db.session.add(book)
        if original:
            book.categories.append(db.session.scalar(db.select(Category).where(Category.slug == 'originals')))
        db.session.add(book)
        source = audio_root / ('immersive.wav' if style == 'Immersive' else 'traditional.wav')
        if source.exists():
            import wave
            with wave.open(str(source)) as audio:
                seconds = audio.getnframes() / audio.getframerate()
            key = 'demo-' + ('immersive.wav' if style == 'Immersive' else 'traditional.wav')
            shutil.copyfile(source, private_root / key)
            book.media.append(MediaAsset(kind='trailer', storage_key=key, mime_type='audio/wav', size_bytes=source.stat().st_size, duration_seconds=seconds))
    db.session.commit()
