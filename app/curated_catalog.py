"""Restore supplied public artwork/preview without publishing full recordings."""
from pathlib import Path
import shutil
from mutagen import File
from .extensions import db
from .models import Audiobook,Author,Category,MediaAsset,now

SLUG='5000-names-of-god'
# Featured titles announced before pricing. Staff add a price, preview and audio later in Shelf studio.
COMING_SOON=[
    {'slug':'victory-unattended','title':'Victory Unattended','genre':('Fiction','fiction'),
     'synopsis':'A Story of a Struggling Boy. A fictional psychological thriller by David Mozie, and a novel of ambition, survival, identity and healing about the cost of success and the search for peace.'},
    {'slug':'5000-acts-of-love','title':'5000 Acts of Love','genre':('Romance','romance'),
     'synopsis':'An audiobook by David Mozie. More about this story is coming soon.'},
    {'slug':'genius-in-the-dungeon','title':'Genius in the Dungeon','genre':('Fiction','fiction'),
     'synopsis':'An audiobook by David Mozie. More about this story is coming soon.'},
    {'slug':'star-among-thorns','title':'Star Among Thorns','genre':('Fiction','fiction'),
     'synopsis':'An audiobook by David Mozie. More about this story is coming soon.'},
    {'slug':'in-gods-hands','title':"In God's Hands",'genre':('Faith & Spirituality','faith-and-spirituality'),
     'synopsis':'An audiobook by David Mozie. More about this story is coming soon.'},
    {'slug':'the-bank-manager','title':'The Bank Manager','genre':('Non-fiction','non-fiction'),
     'synopsis':'An audiobook by David Mozie. More about this story is coming soon.'},
]
# Children's audiobooks by David Mozie, shown on the Children's shelf as well as Featured.
CHILDREN=[
    ('dreams-need-hard-work','Dreams Need Hard Work','big dreams and the steady effort it takes to reach them'),
    ('reading-is-important','Reading Is Important','the joy of books and why reading helps us grow'),
    ('the-importance-of-going-to-school','The Importance of Going to School','learning, friendship and everything school has to offer'),
    ('why-i-must-take-care-of-my-schoolbooks','Why I Must Take Care of My Schoolbooks','looking after the books that help us learn'),
    ('the-secret-of-being-kind','The Secret of Being Kind','how small acts of kindness make a big difference'),
    ('why-i-must-learn-about-germs','Why I Must Learn About Germs','germs, handwashing and staying healthy'),
    ('wisdom-begins-with-listening','Wisdom Begins With Listening','listening to others and learning from their stories'),
    ('the-truth-always-matters','The Truth Always Matters','owning up and telling the truth, even when it is hard'),
    ('the-reward-of-hard-work','The Reward of Hard Work','patience, effort and the pride of a job well done'),
    ('the-beauty-of-being-honest','The Beauty of Being Honest','doing the right thing when no one is asking you to'),
    ('why-i-must-keep-clean','Why I Must Keep Clean','everyday habits that keep us clean and healthy'),
    ('why-i-must-be-a-child-of-good-character','Why I Must Be a Child of Good Character','respect, helpfulness and good manners'),
]
COMING_SOON+=[{'slug':slug,'title':title,'genre':('Children’s','children'),'children':True,
    'synopsis':f'A children’s audiobook by David Mozie about {theme}. More about this story is coming soon.'} for slug,title,theme in CHILDREN]

def copy_asset(app,book,folder,kind,filename,mime):
    source=Path(app.root_path)/'catalog_assets'/folder/filename
    if not source.is_file():
        return
    root=Path(app.config['MEDIA_ROOT']);root.mkdir(parents=True,exist_ok=True)
    key=folder+'-'+filename
    shutil.copyfile(source,root/key)
    if not book.asset(kind):
        duration=File(source).info.length if kind=='trailer' else 0
        book.media.append(MediaAsset(kind=kind,storage_key=key,mime_type=mime,size_bytes=source.stat().st_size,duration_seconds=duration))

def restore_coming_soon(app,author,spec):
    book=db.session.scalar(db.select(Audiobook).where(Audiobook.slug==spec['slug']))
    if not book:
        name,slug=spec['genre']
        category=db.session.scalar(db.select(Category).where(Category.slug==slug))
        if not category:
            category=Category(name=name,slug=slug);db.session.add(category)
        book=Audiobook(slug=spec['slug'],title=spec['title'],author=author,categories=[category],synopsis=spec['synopsis'],language='English',production_style='Narrated',state='published',saleable=False,featured=True,hero=False,homepage_visible=True,price_minor=0,currency='gbp',published_at=now(),children=spec.get('children',False))
        db.session.add(book);db.session.flush()
    copy_asset(app,book,spec['slug'],'cover','cover.jpeg','image/jpeg')
    return book

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
        book=Audiobook(slug=SLUG,title='5000 Names of God',author=author,categories=[category],synopsis='An audiobook by David Mozie exploring the names and attributes of God.',language='English',production_style='Immersive',state='published',saleable=False,featured=True,hero=True,homepage_visible=True,duration_minutes=208,price_minor=0,currency='gbp',published_at=now())
        db.session.add(book)
    db.session.flush()
    for kind,filename,mime in [('cover','cover.jpeg','image/jpeg'),('trailer','preview.mp3','audio/mpeg')]:
        copy_asset(app,book,SLUG,kind,filename,mime)
    for spec in COMING_SOON:
        restore_coming_soon(app,author,spec)
    db.session.commit()
    return book
