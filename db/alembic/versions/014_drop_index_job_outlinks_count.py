"""Drop unused index job outlinks_count column.

Revision ID: 014
Revises: 013
Create Date: 2026-06-14
"""

from alembic import op


revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE index_jobs DROP COLUMN IF EXISTS outlinks_count")


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported")
