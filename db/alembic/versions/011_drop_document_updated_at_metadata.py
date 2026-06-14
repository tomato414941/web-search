"""Drop document updated_at metadata column.

Revision ID: 011
Revises: 010
Create Date: 2026-06-14
"""

from alembic import op


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS updated_at")


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported")
