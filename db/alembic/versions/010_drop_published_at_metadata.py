"""Drop published_at metadata columns.

Revision ID: 010
Revises: 009
Create Date: 2026-06-14
"""

from alembic import op


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS published_at")
    op.execute("ALTER TABLE index_jobs DROP COLUMN IF EXISTS published_at")


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported")
