"""Aggregate analytics events, written once the visitor already has their page."""
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from ..extensions import db
from ..models import AnalyticsEvent

def record_after_response(response, **fields):
    # The database sits in another region, so writing during the request would delay every page.
    app = current_app._get_current_object()
    def write():
        with app.app_context():
            try:
                db.session.add(AnalyticsEvent(**fields))
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                app.logger.warning('Could not record aggregate page engagement.')
    response.call_on_close(write)
    return response
