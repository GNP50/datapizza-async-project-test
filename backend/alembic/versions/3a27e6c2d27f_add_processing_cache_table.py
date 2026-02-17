"""add_processing_cache_table

Revision ID: 3a27e6c2d27f
Revises: 69dcf36319a1
Create Date: 2026-02-13 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '3a27e6c2d27f'
down_revision = '69dcf36319a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create processing_cache table for idempotent operations
    op.create_table('processing_cache',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('cache_key', sa.String(length=64), nullable=False),
        sa.Column('stage', sa.String(length=50), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('result_data', sa.JSON(), nullable=False),
        sa.Column('processing_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for efficient lookups
    op.create_index(op.f('ix_processing_cache_cache_key'), 'processing_cache', ['cache_key'], unique=True)
    op.create_index(op.f('ix_processing_cache_document_id'), 'processing_cache', ['document_id'], unique=False)
    op.create_index(op.f('ix_processing_cache_stage'), 'processing_cache', ['stage'], unique=False)
    op.create_index('ix_processing_cache_content_hash_stage', 'processing_cache', ['content_hash', 'stage'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_processing_cache_content_hash_stage', table_name='processing_cache')
    op.drop_index(op.f('ix_processing_cache_stage'), table_name='processing_cache')
    op.drop_index(op.f('ix_processing_cache_document_id'), table_name='processing_cache')
    op.drop_index(op.f('ix_processing_cache_cache_key'), table_name='processing_cache')
    op.drop_table('processing_cache')
