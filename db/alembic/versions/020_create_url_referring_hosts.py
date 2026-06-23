"""Create observed URL referring host table.

Revision ID: 020
Revises: 019
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS url_referring_hosts (
            dst_url TEXT NOT NULL,
            referring_host TEXT NOT NULL,
            first_observed_at TIMESTAMP NOT NULL DEFAULT NOW(),
            last_observed_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (dst_url, referring_host)
        )
    """)


def downgrade() -> None:
    pass
