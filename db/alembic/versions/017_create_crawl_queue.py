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
            url_hash TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            domain TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_crawl_queue_created "
        "ON crawl_queue(created_at, url_hash)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_crawl_queue_domain ON crawl_queue(domain)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS crawl_queue CASCADE")
