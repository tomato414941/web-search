"""Create search telemetry tables.

Revision ID: 003
Revises: 002
Create Date: 2026-05-27
"""

from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS search_events CASCADE")
    op.execute("DROP TABLE IF EXISTS search_logs CASCADE")

    op.execute("""
        CREATE TABLE IF NOT EXISTS search_requests (
            id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            query_norm TEXT NOT NULL,
            source TEXT NOT NULL,
            mode TEXT NOT NULL,
            page INTEGER NOT NULL,
            result_limit INTEGER NOT NULL,
            result_count INTEGER NOT NULL,
            latency_ms INTEGER,
            session_hash TEXT,
            user_agent TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_search_requests_created "
        "ON search_requests(created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_search_requests_query_created "
        "ON search_requests(query_norm, created_at)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS search_result_impressions (
            id TEXT PRIMARY KEY,
            search_request_id TEXT NOT NULL REFERENCES search_requests(id) ON DELETE CASCADE,
            rank INTEGER NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            score REAL,
            snippet_hash TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_search_result_impressions_request "
        "ON search_result_impressions(search_request_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_search_result_impressions_url "
        "ON search_result_impressions(url)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS search_result_clicks (
            id TEXT PRIMARY KEY,
            search_request_id TEXT NOT NULL REFERENCES search_requests(id) ON DELETE CASCADE,
            impression_id TEXT NOT NULL REFERENCES search_result_impressions(id) ON DELETE CASCADE,
            session_hash TEXT,
            clicked_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_search_result_clicks_request "
        "ON search_result_clicks(search_request_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_search_result_clicks_clicked_at "
        "ON search_result_clicks(clicked_at)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_search_result_clicks_impression_session "
        "ON search_result_clicks(impression_id, COALESCE(session_hash, ''))"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS search_result_clicks CASCADE")
    op.execute("DROP TABLE IF EXISTS search_result_impressions CASCADE")
    op.execute("DROP TABLE IF EXISTS search_requests CASCADE")
