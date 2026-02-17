"""add_web_search_enabled_to_documents

Revision ID: 4cbce8ba6515
Revises: 46ccfbe1b629
Create Date: 2026-02-13 20:37:13.782976

"""
from alembic import op
import sqlalchemy as sa


revision = '4cbce8ba6515'
down_revision = '46ccfbe1b629'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add web_search_enabled column with default True for existing documents
    op.add_column('documents', sa.Column('web_search_enabled', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    # Remove web_search_enabled column
    op.drop_column('documents', 'web_search_enabled')
