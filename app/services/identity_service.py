"""Canonical UUIDs, retaining references from pre-migration URLs and sessions."""
from uuid import UUID
from ..extensions import db
from ..models import LegacyUuidMap

def resolve_id(table, value):
    if isinstance(value, int) or (isinstance(value, str) and value.isdigit() and len(value) < 20):
        mapping = db.session.get(LegacyUuidMap, (table, int(value)))
        return mapping.uuid if mapping else None
    try:
        return UUID(str(value)).hex
    except (ValueError, TypeError, AttributeError):
        return None
