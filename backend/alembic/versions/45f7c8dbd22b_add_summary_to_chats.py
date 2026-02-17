"""add_summary_to_chats

Revision ID: 45f7c8dbd22b
Revises: 3a27e6c2d27f
Create Date: 2026-02-13 10:23:21.420585

"""
from alembic import op
import sqlalchemy as sa


revision = '45f7c8dbd22b'
down_revision = '3a27e6c2d27f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('chats', sa.Column('summary', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('chats', 'summary')
