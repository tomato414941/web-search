"""Add planner-order frontier indexes for ready candidate selection.

The frontier planner orders ready work by:

    priority_bucket,
    priority_score DESC,
    next_fetch_at,
    last_success_at NULLS FIRST,
    discovered_at,
    url_hash

Existing indexes start with ``next_fetch_at`` or ``crawl_profile, next_fetch_at``,
which does not match the planner order. On production this causes a large
parallel sequential scan and top-N sort for every planner pass. Add partial
indexes that match the planner order so the scheduler can stop early when it
only needs a small candidate window.

Revision ID: 016
Revises: 015
Create Date: 2026-03-20
"""

from typing import Sequence, Union

from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PLANNER_READY_INDEX = "idx_frontier_pending_planner_order"
PLANNER_PROFILE_READY_INDEX = "idx_frontier_profile_planner_order"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {PLANNER_READY_INDEX} "
            "ON frontier_entries("
            "priority_bucket, "
            "priority_score DESC, "
            "next_fetch_at, "
            "last_success_at ASC NULLS FIRST, "
            "discovered_at, "
            "url_hash"
            ") "
            "INCLUDE (url, domain, lease_expires_at) "
            "WHERE status = 'pending'"
        )
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {PLANNER_PROFILE_READY_INDEX} "
            "ON frontier_entries("
            "crawl_profile, "
            "priority_bucket, "
            "priority_score DESC, "
            "next_fetch_at, "
            "last_success_at ASC NULLS FIRST, "
            "discovered_at, "
            "url_hash"
            ") "
            "INCLUDE (url, domain, lease_expires_at) "
            "WHERE status = 'pending'"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {PLANNER_PROFILE_READY_INDEX}")
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {PLANNER_READY_INDEX}")
