"""Drop unused index job content_hash column.

Revision ID: 012
Revises: 011
Create Date: 2026-06-14
"""

from alembic import op


revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE index_jobs DROP COLUMN IF EXISTS content_hash")


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported")
