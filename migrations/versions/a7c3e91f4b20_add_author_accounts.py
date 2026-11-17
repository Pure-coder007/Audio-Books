"""Add author accounts for subscription plans, link production enquiries to the author who sent them, and add password reset links.

Revision ID: a7c3e91f4b20
Revises: b4d2e8a1c937
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7c3e91f4b20'
down_revision = 'b4d2e8a1c937'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('author_account',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('email', sa.String(length=254), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('plan', sa.String(length=20), nullable=False, server_default='author'),
        sa.Column('pen_name', sa.String(length=150), nullable=True),
        sa.Column('session_version', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'))
    op.create_table('password_reset',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('account_type', sa.String(length=10), nullable=False),
        sa.Column('account_id', sa.String(length=32), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'))
    op.create_index('ix_password_reset_account_id', 'password_reset', ['account_id'])
    with op.batch_alter_table('production_enquiry') as batch:
        batch.add_column(sa.Column('author_account_id', sa.String(length=32), nullable=True))
        batch.create_index('ix_production_enquiry_author_account_id', ['author_account_id'])
        batch.create_foreign_key('fk_production_enquiry_author_account', 'author_account', ['author_account_id'], ['id'])


def downgrade():
    with op.batch_alter_table('production_enquiry') as batch:
        batch.drop_constraint('fk_production_enquiry_author_account', type_='foreignkey')
        batch.drop_index('ix_production_enquiry_author_account_id')
        batch.drop_column('author_account_id')
    op.drop_index('ix_password_reset_account_id', table_name='password_reset')
    op.drop_table('password_reset')
    op.drop_table('author_account')
