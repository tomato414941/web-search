"""Drop author and organization metadata columns.

Revision ID: 009
Revises: 008
Create Date: 2026-06-14
"""

from alembic import op


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE documents
        DROP COLUMN IF EXISTS author,
        DROP COLUMN IF EXISTS organization
        """
    )
    op.execute(
        """
        ALTER TABLE index_jobs
        DROP COLUMN IF EXISTS author,
        DROP COLUMN IF EXISTS organization
        """
    )


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported")
