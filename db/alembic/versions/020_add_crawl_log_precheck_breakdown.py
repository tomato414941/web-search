"""Add precheck breakdown timing columns to crawl_logs.

Revision ID: 020
Revises: 019
Create Date: 2026-04-05
"""

from typing import Sequence, Union

from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE crawl_logs ADD COLUMN IF NOT EXISTS robots_ms INTEGER")
    op.execute("ALTER TABLE crawl_logs ADD COLUMN IF NOT EXISTS ssrf_ms INTEGER")
    op.execute("ALTER TABLE crawl_logs ADD COLUMN IF NOT EXISTS crawl_delay_ms INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE crawl_logs DROP COLUMN IF EXISTS crawl_delay_ms")
    op.execute("ALTER TABLE crawl_logs DROP COLUMN IF EXISTS ssrf_ms")
    op.execute("ALTER TABLE crawl_logs DROP COLUMN IF EXISTS robots_ms")
