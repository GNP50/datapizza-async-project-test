"""add_summary_to_documents

Revision ID: 2837e0bdc452
Revises: 4cbce8ba6515
Create Date: 2026-02-14 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '2837e0bdc452'
down_revision = '4cbce8ba6515'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('summary', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('documents', 'summary')
