"""Local genre imagery; unknown admin-created genres inherit the library theme."""
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

def genre_theme(slug):
    key, tagline, description = THEMES.get(slug, ('library', 'Find your next favourite.', 'A new shelf of stories to explore.'))
    return {'key': key, 'tagline': tagline, 'description': description, 'image': f'images/genres/{key}.jpg'}
