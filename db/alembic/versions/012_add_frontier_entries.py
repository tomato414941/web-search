"""Add frontier_entries table for priority-aware crawl planning.

Revision ID: 012
Revises: 011
Create Date: 2026-03-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS frontier_entries (
            url_hash TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            domain TEXT NOT NULL,
            normalized_url TEXT NOT NULL,
            discovered_at INTEGER NOT NULL,
            discovered_via TEXT NOT NULL,
            discovery_depth INTEGER NOT NULL DEFAULT 0,
            is_seed BOOLEAN NOT NULL DEFAULT FALSE,
            canonical_source TEXT,
            crawl_profile TEXT NOT NULL,
            priority_bucket SMALLINT NOT NULL,
            priority_score DOUBLE PRECISION NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            next_fetch_at INTEGER NOT NULL,
            last_fetched_at INTEGER,
            last_success_at INTEGER,
            last_status TEXT,
            fail_streak INTEGER NOT NULL DEFAULT 0,
            lease_token TEXT,
            lease_expires_at INTEGER,
            etag TEXT,
            last_modified TEXT,
            content_hash TEXT,
            outlinks_last_discovered INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_frontier_ready
        ON frontier_entries (status, next_fetch_at, priority_bucket, priority_score DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_frontier_domain_ready
        ON frontier_entries (domain, status, next_fetch_at)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_frontier_domain_ready")
    op.execute("DROP INDEX IF EXISTS idx_frontier_ready")
    op.execute("DROP TABLE IF EXISTS frontier_entries")
