"""Local genre imagery; unknown admin-created genres inherit the library theme."""
from functools import cache
from pathlib import Path
from PIL import Image

THEMES = {
    'fiction': ('fiction', 'Somewhere beyond the everyday.', 'Forest paths and worlds waiting to be discovered.'),
    'non-fiction': ('non-fiction', 'Follow a new perspective.', 'Real lives, fresh ideas, and journeys of discovery.'),
    'drama': ('drama', 'Every voice has a story.', 'Powerful performances. Stories that stay with you.'),
    'romance': ('romance', 'Let your heart lead.', 'Tender moments, unexpected connections, and new beginnings.'),
    'children': ('children', 'Little ears. Big adventures.', 'Colourful worlds for curious young imaginations.'),
    'educational': ('educational', 'A little more curious.', 'Listen, learn, and see the world a little differently.'),
    'originals': ('originals', 'Made to be heard.', 'Distinctive stories and productions from MyAudioShelf.'),
    'horror': ('horror', 'Listen with the lights on.', 'Gothic castles, whispered secrets, and stories after dark.'),
}

# Search title, meta description and the introduction shown on each genre page.
COPY = {
    'fiction': ('Fiction Audiobooks – Novels & Stories to Hear',
        'Fiction audiobooks to get lost in, from psychological thrillers to new novels. Play a free preview, then buy and stream in your browser on MyAudioShelf.',
        'Fiction on MyAudioShelf is chosen for the ear: stories with strong characters and a voice worth following. Every title has its own page with the narrator, running time and, where available, a free preview of up to 60 seconds, so you can hear the performance before you buy.'),
    'non-fiction': ('Non-fiction Audiobooks – Ideas, Wisdom & Real Life',
        'Non-fiction audiobooks with practical wisdom and fresh perspectives. Play a free preview, buy without an account and stream in your browser on MyAudioShelf.',
        'Non-fiction audiobooks share real ideas, lessons and experience. They suit listening well: take in a chapter on a walk or a commute and come back to it later, because your purchased audiobooks remember where you stopped.'),
    'drama': ('Drama Audiobooks & Dramatised Audio',
        'Drama audiobooks and dramatised productions with character performances, sound design and music. Play free previews on MyAudioShelf.',
        'Drama is about performance: stories where character voices, pacing and sound carry the emotion. A dramatised production can bring in several actors, ambience and music, while a single skilled narrator can give a classic reading the same intensity.'),
    'romance': ('Romance Audiobooks – Love Stories to Listen To',
        'Romance audiobooks about love, connection and new beginnings. Play a free preview, then buy and stream in your browser on MyAudioShelf.',
        'Romance lives in the voice: the hesitation before a confession, the warmth of a reunion. These audiobooks are chosen for performances that give the relationships room to breathe.'),
    'children': ('Children’s Audiobooks – Stories for Kids',
        'Children’s audiobooks with warm, clear storytelling about kindness, honesty, school and healthy habits. Discover stories for young listeners on MyAudioShelf.',
        'Our children’s audiobooks are gentle stories about the things that matter in a young life: kindness, honesty, hard work, school and staying healthy. They are made to be shared at bedtime, on the school run or in the classroom, and many are on their way to the shelf now.'),
    'educational': ('Educational Audiobooks for Learning by Listening',
        'Educational audiobooks that make learning something you can listen to, at home, in class or on the move. Play free previews on MyAudioShelf.',
        'Educational audio turns learning into listening. These titles are produced to be clear, well paced and easy to follow, whether you are listening on your own or with a class.'),
    'originals': ('MyAudioShelf Originals – Original Audiobooks',
        'Original audiobooks and audio stories created by MyAudioShelf and produced for listening from the very first page. Play free previews.',
        'MyAudioShelf Originals are stories we develop and produce ourselves, made for the ear from the beginning rather than adapted afterwards.'),
    'horror': ('Horror Audiobooks – Listen With the Lights On',
        'Horror and gothic audiobooks with atmosphere you can hear: whispered secrets, creaking houses and stories best heard after dark. Play free previews on MyAudioShelf.',
        'Horror is made for audio. A voice close to your ear and a carefully placed sound can unsettle more than anything on a page. Listen with headphones, and perhaps with the lights on.'),
    'faith-and-spirituality': ('Faith & Spirituality Audiobooks',
        'Faith and spirituality audiobooks for prayer, study and reflection. Play a free preview, then buy and listen in your browser on MyAudioShelf.',
        'Faith and spirituality audiobooks for quiet reflection, study and devotion. Listening lets you return to a passage again and again: in the car, on a walk or at the start of the day.'),
    'wisdom-inspiration': ('Inspirational Audiobooks – Wisdom & Encouragement',
        'Inspirational audiobooks on wisdom, love and resilience: short, thoughtful listens for every day. Play a free preview on MyAudioShelf.',
        'Wisdom and inspiration audiobooks are short, thoughtful listens: reflections, poetry and practical wisdom to return to whenever you need encouragement.'),
    'writing-publishing': ('Writing & Publishing Audiobooks for Authors',
        'Audiobooks about writing and publishing for authors who want to finish, publish and share their work. Play a free preview on MyAudioShelf.',
        'Books for writers about the craft, and the risks, of writing and publishing. Thinking about an audiobook of your own? Our guides explain how to prepare a manuscript for production.'),
}


@cache
def image_size(name):
    with Image.open(Path(__file__).parent / 'static' / 'images' / 'genres' / name) as image:
        return image.size


def genre_theme(slug):
    key, tagline, description = THEMES.get(slug, ('library', 'Find your next favourite.', 'A new shelf of stories to explore.'))
    small = f'{key}-800.webp'
    width, height = image_size(small)
    return {'key': key, 'tagline': tagline, 'description': description, 'image': f'images/genres/{key}.jpg',
        'small': f'images/genres/{small}', 'large': f'images/genres/{key}-1600.webp', 'width': width, 'height': height}


def genre_copy(genre):
    title, description, intro = COPY.get(genre.slug) or (f'{genre.name} Audiobooks',
        f'Browse {genre.name} audiobooks on MyAudioShelf. Play free previews, buy without an account and stream in your browser.',
        genre_theme(genre.slug)['description'])
    return {'title': title, 'description': description, 'intro': intro}
