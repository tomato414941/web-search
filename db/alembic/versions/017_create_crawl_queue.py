"""Create crawl_queue table.

Revision ID: 017
Revises: 016
Create Date: 2026-06-16
"""

from typing import Sequence, Union

from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS crawl_queue (
            url_hash TEXT PRIMARY KEY REFERENCES urls(url_hash) ON DELETE CASCADE,
            created_at INTEGER NOT NULL
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_crawl_queue_created "
        "ON crawl_queue(created_at, url_hash)"
    )
    op.execute("""
        INSERT INTO crawl_queue (url_hash, created_at)
        SELECT schedule.url_hash, schedule.discovered_at
        FROM crawl_schedule AS schedule
        JOIN urls ON urls.url_hash = schedule.url_hash
        WHERE schedule.status = 'pending'
        ON CONFLICT (url_hash) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS crawl_queue CASCADE")
