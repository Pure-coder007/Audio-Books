"""Convert internal integer identities and references to UUIDs without losing rows.

Revision ID: ab614dc72a19
Revises: def0a29aa309
"""
from uuid import uuid5, NAMESPACE_URL
from alembic import op
import sqlalchemy as sa

revision='ab614dc72a19'
down_revision='def0a29aa309'
branch_labels=None
depends_on=None


def upgrade():
    connection=op.get_bind()
    sqlite=connection.dialect.name=='sqlite'
    if sqlite:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
    inspector=sa.inspect(connection)
    tables=inspector.get_table_names()
    identities={}
    references={}
    foreign_keys=[]
    for table in tables:
        columns={column['name']:column for column in inspector.get_columns(table)}
        if 'id' in columns and isinstance(columns['id']['type'],sa.Integer):
            identities[table]=[row[0] for row in connection.execute(sa.text(f'SELECT id FROM "{table}"'))]
        for fk in inspector.get_foreign_keys(table):
            foreign_keys.append((table,fk))
            for column in fk['constrained_columns']:
                if isinstance(columns[column]['type'],sa.Integer):
                    references.setdefault(table,{})[column]=fk['referred_table']
    mappings={table:{old:uuid5(NAMESPACE_URL,f'myaudioshelf:{table}:{old}').hex for old in values} for table,values in identities.items()}
    op.create_table('legacy_uuid_map',sa.Column('table_name',sa.String(80),primary_key=True),sa.Column('legacy_id',sa.Integer,primary_key=True),sa.Column('uuid',sa.String(32),nullable=False))
    rows = [dict(table=table, old=old, new=new) for table, values in mappings.items() for old, new in values.items()]
    if rows:
        connection.execute(sa.text('INSERT INTO legacy_uuid_map (table_name,legacy_id,uuid) VALUES (:table,:old,:new)'), rows)
    if not sqlite:
        for table,fk in foreign_keys:op.drop_constraint(fk['name'],table,type_='foreignkey')
    changes={table:{**refs} for table,refs in references.items()}
    for table in identities:changes.setdefault(table,{})['id']=table
    for table,columns in changes.items():
        with op.batch_alter_table(table) as batch:
            for column in columns:
                batch.alter_column(column,type_=sa.String(32),existing_type=sa.Integer(),server_default=None,postgresql_using=f'"{column}"::text')
    for table,columns in changes.items():
        for column,target in columns.items():
            connection.execute(sa.text(f'''UPDATE "{table}" SET "{column}" =
                (SELECT uuid FROM legacy_uuid_map WHERE table_name=:target
                 AND CAST(legacy_id AS VARCHAR)="{table}"."{column}")
                WHERE "{column}" IS NOT NULL'''), dict(target=target))
    if not sqlite:
        for table,fk in foreign_keys:
            op.create_foreign_key(fk['name'],table,fk['referred_table'],fk['constrained_columns'],fk['referred_columns'],**fk.get('options',{}))
    if sqlite:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            if connection.exec_driver_sql('PRAGMA foreign_key_check').fetchone():raise RuntimeError('UUID migration found an invalid reference.')


def downgrade():
    raise RuntimeError('UUID identifiers cannot be downgraded safely. Restore the pre-migration database backup if required.')
