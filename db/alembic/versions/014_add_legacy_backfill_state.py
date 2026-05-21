"""Add legacy backfill state for incremental frontier migration.

Revision ID: 014
Revises: 013
Create Date: 2026-03-19
"""

from typing import Sequence, Union

from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_crawl_queue_backfill_cursor")
    op.execute("DROP TABLE IF EXISTS legacy_backfill_state")
