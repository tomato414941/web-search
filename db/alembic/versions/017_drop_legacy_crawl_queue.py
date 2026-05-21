"""Drop legacy crawl_queue and backfill state tables.

The frontier migration is complete — crawl_queue has been fully drained
into frontier_entries and is no longer needed.

Revision ID: 017
Revises: 016
Create Date: 2026-03-21
"""

from typing import Sequence, Union

from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_crawl_queue_backfill_cursor")
    op.execute("DROP TABLE IF EXISTS legacy_backfill_state")
    op.execute("DROP TABLE IF EXISTS crawl_queue")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS crawl_queue (
            url_hash   TEXT PRIMARY KEY,
            url        TEXT NOT NULL,
            domain     TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS legacy_backfill_state (
            state_key TEXT PRIMARY KEY,
            cursor_created_at INTEGER,
            cursor_url_hash TEXT,
            migrated_rows BIGINT NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_crawl_queue_backfill_cursor
        ON crawl_queue (created_at, url_hash)
    """)
