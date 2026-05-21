"""Add partial index for seed listing and counting.

The admin seeds page reads:
- COUNT(*) FROM urls WHERE is_seed = TRUE
- a recent page ordered by created_at DESC

Without a partial index PostgreSQL scans the full urls table, which makes
the cold admin seeds page take multiple seconds on production-sized data.

Revision ID: 011
Revises: 010
Create Date: 2026-03-09
"""

from typing import Sequence, Union

from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "idx_urls_seed_created_at"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
            "ON urls(created_at DESC) "
            "INCLUDE (url, domain, crawl_count, last_crawled_at) "
            "WHERE is_seed = TRUE"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}")
