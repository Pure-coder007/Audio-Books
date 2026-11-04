"""Search metadata: page descriptions, canonical listings and schema.org structured data."""
import re
from flask import current_app, url_for

# Wording the catalogue uses until a real description is written. Pages that still show it stay out of search results.
PLACEHOLDER_SYNOPSIS = 'More about this story is coming soon.'
# The defaults the bookshelf form submits; they do not change the listing.
DEFAULT_ARGS = {'sort': 'newest', 'search': 'all'}


def absolute(path):
    return current_app.config['BASE_URL'] + path


def summary(text, limit=158):
    """Shorten text for a meta description at a word boundary."""
    text = ' '.join((text or '').split())
    if len(text) <= limit:
        return text
    # End on a whole sentence when one fills most of the space; otherwise cut at a word.
    sentence = max(text.rfind(mark, 0, limit) for mark in ('. ', '! ', '? '))
    if sentence >= limit * 0.6:
        return text[:sentence + 1]
    cut = text[:limit - 1].rsplit(' ', 1)[0].rstrip(',;:–—-')
    return cut + '…'


def synopsis_text(book):
    return ' '.join((book.synopsis or '').replace(PLACEHOLDER_SYNOPSIS, '').split())


def book_description(book):
    if book.seo_description:
        return summary(book.seo_description)
    story = synopsis_text(book)
    if len(story) >= 120:
        return summary(story)
    # Name the author and narrator unless the synopsis already does.
    credit = '' if book.author.name in story else f'{book.production_style} audiobook by {book.author.name}'
    if book.narrator and book.narrator not in story:
        credit += (', read by the author' if book.narrator == book.author.name else f', narrated by {book.narrator}') if credit else f'Narrated by {book.narrator}'
    close = 'Coming soon to MyAudioShelf.' if book.coming_soon else 'Play a free preview on MyAudioShelf.' if book.asset('trailer') else 'Listen on MyAudioShelf.'
    return summary(' '.join(part for part in [story, credit and credit + '.', close] if part))


def iso_duration(minutes):
    hours, minutes = divmod(int(minutes or 0), 60)
    return 'PT' + (f'{hours}H' if hours else '') + (f'{minutes}M' if minutes or not hours else '')


def listing_state(args, genre_slug, selected_genre, page):
    """Canonical URL and indexing for a bookshelf view. Searches, filters and sorts are left out of the index."""
    used = {key for key, value in args.items() if value and key != 'page' and DEFAULT_ARGS.get(key) != value}
    if genre_slug and args.get('genre') == genre_slug:
        used.discard('genre')
    genre_only = bool(selected_genre) and (bool(genre_slug) or used == {'genre'})
    if used - {'genre'} or (genre_slug and 'genre' in used) or not page.total:
        return None, True
    path = url_for('main.category', genre_slug=selected_genre.slug) if genre_only else url_for('main.catalog')
    return absolute(path + (f'?page={page.page}' if page.page > 1 else '')), False


def organization_ref():
    # Named in full on every page: search engines do not follow an @id to the homepage's Organization.
    return {'@type': 'Organization', '@id': absolute('/#organization'), 'name': 'MyAudioShelf', 'url': absolute('/'),
        'logo': absolute(url_for('static', filename='images/brand/aud-logo.png'))}


def breadcrumbs(*trail):
    """BreadcrumbList for (name, path) pairs; the last item is the current page."""
    return {'@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': index, 'name': name, 'item': absolute(path)} for index, (name, path) in enumerate(trail, 1)]}


def book_schema(book):
    url = absolute(url_for('main.book', slug=book.slug))
    purchasable = book.saleable and book.price_minor > 0 and not book.is_demo
    data = {'@type': ['Audiobook', 'Product'] if purchasable else 'Audiobook', '@id': url + '#audiobook', 'name': book.title, 'url': url,
        'image': absolute(book.cover_url), 'description': synopsis_text(book) or book_description(book), 'bookFormat': 'https://schema.org/AudiobookFormat',
        'author': {'@type': 'Person', 'name': book.author.name, 'url': absolute(url_for('main.author', slug=book.author.slug))},
        'inLanguage': book.language, 'genre': [category.name for category in book.categories]}
    if book.narrator:
        data['readBy'] = {'@type': 'Person', 'name': book.narrator}
    if book.duration_minutes:
        data['duration'] = iso_duration(book.duration_minutes)
    if book.publisher:
        data['publisher'] = {'@type': 'Organization', 'name': book.publisher}
    if book.published_at and not book.coming_soon:
        data['datePublished'] = book.published_at.date().isoformat()
    trailer = book.asset('trailer')
    if trailer:
        data['audio'] = {'@type': 'AudioObject', 'name': f'{book.title}: audiobook preview', 'contentUrl': absolute(url_for('main.public_media', media_id=trailer.id)),
            'encodingFormat': trailer.mime_type, 'duration': f'PT{round(trailer.duration_seconds or 0)}S'}
    if purchasable:
        # Matches the Merchant Center feed: same id, price, brand and no-returns policy.
        data.update({'sku': book.id, 'brand': {'@type': 'Brand', 'name': 'MyAudioShelf'}, 'offers': {'@type': 'Offer', 'url': url,
            'price': f'{book.price_minor / 100:.2f}', 'priceCurrency': book.currency.upper(), 'availability': 'https://schema.org/InStock',
            'seller': organization_ref(),
            'hasMerchantReturnPolicy': {'@type': 'MerchantReturnPolicy', 'applicableCountry': 'GB', 'returnPolicyCategory': 'https://schema.org/MerchantReturnNotPermitted'},
            'shippingDetails': {'@type': 'OfferShippingDetails', 'shippingRate': {'@type': 'MonetaryAmount', 'value': 0, 'currency': book.currency.upper()},
                'shippingDestination': {'@type': 'DefinedRegion', 'addressCountry': 'GB'},
                'deliveryTime': {'@type': 'ShippingDeliveryTime', 'handlingTime': {'@type': 'QuantitativeValue', 'minValue': 0, 'maxValue': 0, 'unitCode': 'DAY'},
                    'transitTime': {'@type': 'QuantitativeValue', 'minValue': 0, 'maxValue': 0, 'unitCode': 'DAY'}}}}})
    return data


def graph(*items):
    return {'@context': 'https://schema.org', '@graph': [item for item in items if item]}
