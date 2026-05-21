"""Add stage timing columns to crawl_logs.

Revision ID: 019
Revises: 018
Create Date: 2026-04-05
"""

from typing import Sequence, Union

from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE crawl_logs ADD COLUMN IF NOT EXISTS precheck_ms INTEGER")
    op.execute("ALTER TABLE crawl_logs ADD COLUMN IF NOT EXISTS fetch_ms INTEGER")
    op.execute("ALTER TABLE crawl_logs ADD COLUMN IF NOT EXISTS parse_ms INTEGER")
    op.execute("ALTER TABLE crawl_logs ADD COLUMN IF NOT EXISTS submit_ms INTEGER")
    op.execute("ALTER TABLE crawl_logs ADD COLUMN IF NOT EXISTS total_ms INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE crawl_logs DROP COLUMN IF EXISTS total_ms")
    op.execute("ALTER TABLE crawl_logs DROP COLUMN IF EXISTS submit_ms")
    op.execute("ALTER TABLE crawl_logs DROP COLUMN IF EXISTS parse_ms")
    op.execute("ALTER TABLE crawl_logs DROP COLUMN IF EXISTS fetch_ms")
    op.execute("ALTER TABLE crawl_logs DROP COLUMN IF EXISTS precheck_ms")
