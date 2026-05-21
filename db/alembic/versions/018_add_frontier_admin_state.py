"""Add persisted frontier admin counters and snapshots.

Revision ID: 018
Revises: 017
Create Date: 2026-03-21
"""

from typing import Sequence, Union

from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS frontier_counters (
            name TEXT PRIMARY KEY,
            pending_rows BIGINT NOT NULL DEFAULT 0,
            leased_rows BIGINT NOT NULL DEFAULT 0,
            frontier_rows BIGINT NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS frontier_snapshot (
            name TEXT PRIMARY KEY,
            generated_at INTEGER,
            snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            last_error TEXT,
            updated_at INTEGER NOT NULL
        )
    """)
    op.execute("""
        INSERT INTO frontier_counters (
            name,
            pending_rows,
            leased_rows,
            frontier_rows,
            updated_at
        )
        SELECT
            'frontier',
            COUNT(*) FILTER (WHERE status = 'pending'),
            COUNT(*) FILTER (WHERE status = 'leased'),
            COUNT(*),
            EXTRACT(EPOCH FROM NOW())::INTEGER
        FROM frontier_entries
        ON CONFLICT (name) DO UPDATE SET
            pending_rows = EXCLUDED.pending_rows,
            leased_rows = EXCLUDED.leased_rows,
            frontier_rows = EXCLUDED.frontier_rows,
            updated_at = EXCLUDED.updated_at
    """)
    op.execute("""
        INSERT INTO frontier_snapshot (
            name,
            generated_at,
            snapshot_json,
            last_error,
            updated_at
        )
        VALUES (
            'frontier',
            NULL,
            '{}'::jsonb,
            NULL,
            EXTRACT(EPOCH FROM NOW())::INTEGER
        )
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS frontier_snapshot")
    op.execute("DROP TABLE IF EXISTS frontier_counters")
