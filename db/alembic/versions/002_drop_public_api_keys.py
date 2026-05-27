"""Drop public API key tracking.

Revision ID: 002
Revises: 001
Create Date: 2026-05-27
"""

from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_search_logs_api_key")
    op.execute("ALTER TABLE search_logs DROP COLUMN IF EXISTS api_key_id")
    op.execute("DROP TABLE IF EXISTS api_keys CASCADE")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id TEXT PRIMARY KEY,
            key_hash TEXT NOT NULL UNIQUE,
            key_prefix TEXT NOT NULL,
            name TEXT NOT NULL,
            rate_limit_daily INTEGER NOT NULL DEFAULT 1000,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            last_used_at TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_status ON api_keys(status)")
    op.execute("ALTER TABLE search_logs ADD COLUMN IF NOT EXISTS api_key_id TEXT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_search_logs_api_key ON search_logs(api_key_id)"
    )
