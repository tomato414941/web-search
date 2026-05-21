"""Add fetch breakdown timing columns to crawl_logs.

Revision ID: 021
Revises: 020
Create Date: 2026-04-05
"""

from typing import Sequence, Union

from alembic import op

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE crawl_logs ADD COLUMN IF NOT EXISTS fetch_request_ms INTEGER"
    )
    op.execute(
        "ALTER TABLE crawl_logs ADD COLUMN IF NOT EXISTS fetch_body_read_ms INTEGER"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE crawl_logs DROP COLUMN IF EXISTS fetch_body_read_ms")
    op.execute("ALTER TABLE crawl_logs DROP COLUMN IF EXISTS fetch_request_ms")
