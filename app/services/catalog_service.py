"""Removing audiobooks from the catalogue without breaking anyone's purchases."""
from ..extensions import db
from ..models import Audiobook, Author, OrderItem, PurchaseEntitlement, ListeningProgress, AnalyticsEvent

# The biography seed.py gives its fictional authors.
SAMPLE_AUTHOR_BIO = 'A fictional author profile created to demonstrate the MyAudioShelf experience.'


def times_bought(book):
    """Orders and library entitlements that refer to the book; such a book is kept so receipts and libraries still work."""
    return db.session.scalar(db.select(db.func.count()).select_from(OrderItem).where(OrderItem.book_id == book.id)) + \
        db.session.scalar(db.select(db.func.count()).select_from(PurchaseEntitlement).where(PurchaseEntitlement.book_id == book.id))


def delete_audiobook(book):
    """Delete a book nobody has bought, with its media records, chapters and listening progress. The caller commits."""
    db.session.execute(db.delete(ListeningProgress).where(ListeningProgress.book_id == book.id))
    db.session.execute(db.update(AnalyticsEvent).where(AnalyticsEvent.book_id == book.id).values(book_id=None))
    db.session.delete(book)


def remove_samples():
    """Delete the fictional sample titles and their authors. A sample on a past order is archived instead."""
    for book in db.session.scalars(db.select(Audiobook).where(Audiobook.is_demo.is_(True))).all():
        if times_bought(book):
            book.state, book.hero, book.featured, book.homepage_visible, book.saleable = 'archived', False, False, False, False
        else:
            delete_audiobook(book)
    db.session.flush()
    for author in db.session.scalars(db.select(Author).where(Author.bio.startswith(SAMPLE_AUTHOR_BIO))).all():
        if not author.books:
            db.session.delete(author)
