"""Add authorship metadata columns to documents and index_jobs tables.

Stores author name, organization, and last-modified date extracted from
HTML metadata (JSON-LD, meta tags). Enables authorship clarity scoring
for AI-agent-optimized ranking.

Revision ID: 008
Revises: 007
Create Date: 2026-03-03
"""

from typing import Sequence, Union

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS author TEXT")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS organization TEXT")
    op.execute("ALTER TABLE index_jobs ADD COLUMN IF NOT EXISTS updated_at TEXT")
    op.execute("ALTER TABLE index_jobs ADD COLUMN IF NOT EXISTS author TEXT")
    op.execute("ALTER TABLE index_jobs ADD COLUMN IF NOT EXISTS organization TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE index_jobs DROP COLUMN IF EXISTS organization")
    op.execute("ALTER TABLE index_jobs DROP COLUMN IF EXISTS author")
    op.execute("ALTER TABLE index_jobs DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS organization")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS author")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS updated_at")
