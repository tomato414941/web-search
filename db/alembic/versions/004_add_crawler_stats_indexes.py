"""Add indexes to improve crawler stats query performance.

- crawl_logs(created_at, status): composite index for status counts and error count queries
- crawl_logs(status, created_at DESC): for recent errors lookup
- urls(last_crawled_at): for active/recent URL count

Revision ID: 004
Revises: 003
Create Date: 2026-03-02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_crawl_logs_created_status "
        "ON crawl_logs(created_at, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_crawl_logs_status_created "
        "ON crawl_logs(status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_urls_last_crawled "
        "ON urls(last_crawled_at) WHERE last_crawled_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_crawl_logs_created_status")
    op.execute("DROP INDEX IF EXISTS idx_crawl_logs_status_created")
    op.execute("DROP INDEX IF EXISTS idx_urls_last_crawled")
