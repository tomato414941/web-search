"""Drop crawl schedule priority_score column.

Revision ID: 005
Revises: 004
Create Date: 2026-06-08
"""

from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE crawl_schedule DROP COLUMN IF EXISTS priority_score")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_crawl_schedule_ready "
        "ON crawl_schedule(status, next_fetch_at, priority_bucket)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_crawl_schedule_pending_planner_order "
        "ON crawl_schedule("
        "priority_bucket, next_fetch_at, "
        "last_success_at ASC NULLS FIRST, discovered_at, url_hash"
        ") INCLUDE (url, domain, lease_expires_at) "
        "WHERE status = 'pending'"
    )


def downgrade() -> None:
    pass
