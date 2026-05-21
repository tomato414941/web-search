"""Add crawl_profile-aware frontier ready index.

The planner now selects ready frontier entries by budget tier and crawl_profile.
The existing idx_frontier_ready index only starts with (status, next_fetch_at),
which leaves the planner scanning large pending ranges before it can narrow by
profile. A profile-aware partial index makes tiered selection cheaper without
changing frontier semantics.

Revision ID: 015
Revises: 014
Create Date: 2026-03-20
"""

from typing import Sequence, Union

from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "idx_frontier_profile_ready"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
            "ON frontier_entries("
            "crawl_profile, "
            "next_fetch_at, "
            "priority_bucket, "
            "priority_score DESC, "
            "last_success_at, "
            "discovered_at, "
            "url_hash"
            ") "
            "WHERE status = 'pending'"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}")
