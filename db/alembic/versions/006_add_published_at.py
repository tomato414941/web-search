"""Add published_at column to documents and index_jobs tables.

Stores the original publication date extracted from HTML metadata
(article:published_time, JSON-LD datePublished, etc).

Revision ID: 006
Revises: 005
Create Date: 2026-03-02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS published_at TIMESTAMP")
    op.execute("ALTER TABLE index_jobs ADD COLUMN IF NOT EXISTS published_at TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE index_jobs DROP COLUMN IF EXISTS published_at")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS published_at")
