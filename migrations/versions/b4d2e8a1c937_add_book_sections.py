"""Add a section to each audiobook for the Translated and Reviewed books pages.

Revision ID: b4d2e8a1c937
Revises: f271b938ca60
"""
from alembic import op
import sqlalchemy as sa

revision = 'b4d2e8a1c937'
down_revision = 'f271b938ca60'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('audiobook') as batch:
        batch.add_column(sa.Column('section', sa.String(length=20), server_default='shelf', nullable=False))


def downgrade():
    with op.batch_alter_table('audiobook') as batch:
        batch.drop_column('section')
