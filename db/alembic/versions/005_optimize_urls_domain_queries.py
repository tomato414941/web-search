"""Optimize domain GROUP BY queries and autovacuum on urls table.

- Add composite index (status, domain) for index-only scans on
  get_pending_domains / get_domains queries (5s -> <1s)
- Drop redundant idx_urls_status (covered by new composite index)
- Tune autovacuum on urls table to run more aggressively

Revision ID: 005
Revises: 004
Create Date: 2026-03-02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_urls_status_domain ON urls(status, domain)"
    )
    op.execute("DROP INDEX IF EXISTS idx_urls_status")
    op.execute(
        "ALTER TABLE urls SET ("
        "autovacuum_vacuum_scale_factor = 0.02, "
        "autovacuum_vacuum_threshold = 100, "
        "autovacuum_analyze_scale_factor = 0.05"
        ")"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE urls RESET (autovacuum_vacuum_scale_factor, autovacuum_vacuum_threshold, autovacuum_analyze_scale_factor)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_urls_status ON urls(status)")
    op.execute("DROP INDEX IF EXISTS idx_urls_status_domain")
