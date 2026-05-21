"""Add domain_state table for durable host planning state.

Revision ID: 013
Revises: 012
Create Date: 2026-03-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS domain_state (
            domain TEXT PRIMARY KEY,
            next_request_at INTEGER NOT NULL DEFAULT 0,
            crawl_delay_sec DOUBLE PRECISION NOT NULL DEFAULT 1.0,
            backoff_until INTEGER,
            fail_streak INTEGER NOT NULL DEFAULT 0,
            inflight_leases INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_domain_state_ready
        ON domain_state (backoff_until, next_request_at)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_domain_state_ready")
    op.execute("DROP TABLE IF EXISTS domain_state")
