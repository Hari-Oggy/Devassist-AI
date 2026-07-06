"""fix columns

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-29 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'reviews' in tables:
        cols = [c['name'] for c in inspector.get_columns('reviews')]
        if 'prologue_json' not in cols:
            op.add_column('reviews', sa.Column('prologue_json', sa.JSON(), nullable=True))

    if 'findings' in tables:
        cols = [c['name'] for c in inspector.get_columns('findings')]
        if 'chapter_id' not in cols:
            op.add_column('findings', sa.Column('chapter_id', sa.Integer(), nullable=True))
            # Wrap foreign key creation in a try-except because we might not easily check if constraint exists
            try:
                op.create_foreign_key('fk_findings_chapter_id', 'findings', 'chapters', ['chapter_id'], ['id'], ondelete='SET NULL')
            except Exception:
                pass

def downgrade() -> None:
    pass
