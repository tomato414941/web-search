"""Optimize urls indexes to enable HOT updates on crawling->done transition.

Replace non-partial idx_urls_status_domain with partial idx_urls_pending_domain.
Drop idx_urls_recrawl and idx_urls_last_crawled (covered by caching).

After this migration, the crawling->done transition (most frequent path)
has ZERO index operations, enabling PostgreSQL HOT updates with fillfactor=70.

Remaining indexes on urls:
- idx_urls_pending_claim(status, priority DESC, created_at) WHERE status = 'pending'
- idx_urls_pending_domain(domain) WHERE status = 'pending'  (NEW)
- idx_urls_domain(domain)

Revision ID: 007
Revises: 006
Create Date: 2026-03-02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_urls_pending_domain "
        "ON urls(domain) WHERE status = 'pending'"
    )
    op.execute("DROP INDEX IF EXISTS idx_urls_status_domain")
    op.execute("DROP INDEX IF EXISTS idx_urls_recrawl")
    op.execute("DROP INDEX IF EXISTS idx_urls_last_crawled")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_urls_last_crawled "
        "ON urls(last_crawled_at) WHERE last_crawled_at IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_urls_recrawl "
        "ON urls(last_crawled_at) WHERE status IN ('done', 'failed')"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_urls_status_domain "
        "ON urls(status, domain)"
    )
    op.execute("DROP INDEX IF EXISTS idx_urls_pending_domain")
