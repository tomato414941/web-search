"""Drop inverted_index, token_stats, and index_stats tables.

These tables were used by the custom PostgreSQL BM25 search implementation.
All search is now handled by OpenSearch, making these tables unnecessary.
Dropping them frees ~30GB of storage.

Revision ID: 003
Revises: 002
Create Date: 2026-02-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS token_stats")
    op.execute("DROP TABLE IF EXISTS index_stats")
    op.execute("DROP TABLE IF EXISTS inverted_index")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS inverted_index (
            token TEXT NOT NULL,
            url TEXT NOT NULL REFERENCES documents(url) ON DELETE CASCADE,
            field TEXT NOT NULL,
            term_freq INTEGER DEFAULT 1,
            PRIMARY KEY (token, url, field)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_inverted_token ON inverted_index(token)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_inverted_url ON inverted_index(url)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS index_stats (
            key TEXT PRIMARY KEY,
            value REAL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS token_stats (
            token TEXT PRIMARY KEY,
            doc_freq INTEGER DEFAULT 0
        )
    """)
