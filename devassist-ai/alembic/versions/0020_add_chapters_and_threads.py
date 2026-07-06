"""add chapters and threads

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-29 19:50:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0020'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # chapters table
    if 'chapters' not in tables:
        op.create_table('chapters',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('review_id', sa.Integer(), nullable=False),
            sa.Column('external_id', sa.String(length=64), nullable=False),
            sa.Column('order', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(length=200), nullable=False),
            sa.Column('summary', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_chapters_external_id'), 'chapters', ['external_id'], unique=False)
        op.create_index(op.f('ix_chapters_review_id'), 'chapters', ['review_id'], unique=False)

    # key_changes table
    if 'key_changes' not in tables:
        op.create_table('key_changes',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('chapter_id', sa.Integer(), nullable=False),
            sa.Column('external_id', sa.String(length=64), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('line_refs_json', sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_key_changes_chapter_id'), 'key_changes', ['chapter_id'], unique=False)
        op.create_index(op.f('ix_key_changes_external_id'), 'key_changes', ['external_id'], unique=False)

    # comment_threads table
    if 'comment_threads' not in tables:
        op.create_table('comment_threads',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('review_id', sa.Integer(), nullable=False),
            sa.Column('file_path', sa.String(length=500), nullable=False),
            sa.Column('line_start', sa.Integer(), nullable=False),
            sa.Column('line_end', sa.Integer(), nullable=False),
            sa.Column('side', sa.String(length=16), nullable=False),
            sa.Column('status', sa.String(length=16), nullable=False),
            sa.Column('github_comment_id', sa.Integer(), nullable=True),
            sa.Column('resolved', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_comment_threads_file_path'), 'comment_threads', ['file_path'], unique=False)
        op.create_index(op.f('ix_comment_threads_review_id'), 'comment_threads', ['review_id'], unique=False)

    # comments table
    if 'comments' not in tables:
        op.create_table('comments',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('thread_id', sa.Integer(), nullable=False),
            sa.Column('author', sa.String(length=200), nullable=False),
            sa.Column('body', sa.Text(), nullable=False),
            sa.Column('is_bot', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['thread_id'], ['comment_threads.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_comments_thread_id'), 'comments', ['thread_id'], unique=False)

    # Alter reviews
    if 'reviews' in tables:
        cols = [c['name'] for c in inspector.get_columns('reviews')]
        if 'prologue_json' not in cols:
            op.add_column('reviews', sa.Column('prologue_json', sa.JSON(), nullable=True))

    # Alter findings
    if 'findings' in tables:
        cols = [c['name'] for c in inspector.get_columns('findings')]
        if 'chapter_id' not in cols:
            op.add_column('findings', sa.Column('chapter_id', sa.Integer(), nullable=True))
            op.create_foreign_key(None, 'findings', 'chapters', ['chapter_id'], ['id'], ondelete='SET NULL')

def downgrade() -> None:
    op.drop_constraint(None, 'findings', type_='foreignkey')
    op.drop_column('findings', 'chapter_id')
    op.drop_column('reviews', 'prologue_json')
    op.drop_table('comments')
    op.drop_table('comment_threads')
    op.drop_table('key_changes')
    op.drop_table('chapters')
