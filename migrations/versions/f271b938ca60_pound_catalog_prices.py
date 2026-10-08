"""Use pounds for catalog prices and enable priced titles for sale.

Revision ID: f271b938ca60
Revises: c83bf19f5d22
"""
from alembic import op

revision = 'f271b938ca60'
down_revision = 'c83bf19f5d22'
branch_labels = None
depends_on = None


def upgrade():
    # Catalog amounts are the owner's entered pound prices. Historical orders
    # retain their original currency and totals for receipts and reconciliation.
    op.execute("UPDATE audiobook SET currency='gbp'")
    op.execute("UPDATE audiobook SET saleable=(price_minor > 0) WHERE is_demo=false AND state <> 'archived'")


def downgrade():
    # Previous catalog currencies cannot be reconstructed safely.
    pass
