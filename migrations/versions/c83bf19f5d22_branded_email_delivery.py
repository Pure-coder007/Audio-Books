"""Add branded receipts and durable Resend delivery metadata.

Revision ID: c83bf19f5d22
Revises: ab614dc72a19
"""
from alembic import op
import sqlalchemy as sa
revision = 'c83bf19f5d22'
down_revision = 'ab614dc72a19'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('email_delivery') as batch:
        batch.add_column(sa.Column('html_body', sa.Text()))
        batch.add_column(sa.Column('order_id', sa.String(32)))
        batch.add_column(sa.Column('link_expires_at', sa.DateTime()))
        batch.add_column(sa.Column('delivery_key', sa.String(32)))
        batch.add_column(sa.Column('claimed_until', sa.DateTime()))
        batch.add_column(sa.Column('provider_message_id', sa.String(255)))
        batch.add_column(sa.Column('sent_at', sa.DateTime()))
        batch.add_column(sa.Column('last_error', sa.String(100)))
        batch.create_foreign_key('fk_email_delivery_order_id', 'order', ['order_id'], ['id'])
    op.execute('UPDATE email_delivery SET delivery_key=id')
    with op.batch_alter_table('email_delivery') as batch:
        batch.alter_column('delivery_key', existing_type=sa.String(32), nullable=False)

def downgrade():
    with op.batch_alter_table('email_delivery') as batch:
        batch.drop_constraint('fk_email_delivery_order_id', type_='foreignkey')
        for column in ['html_body','order_id','link_expires_at','delivery_key','claimed_until','provider_message_id','sent_at','last_error']:
            batch.drop_column(column)
