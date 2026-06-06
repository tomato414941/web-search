"""Drop URL ledger crawl execution state.

Revision ID: 005
Revises: 004
Create Date: 2026-06-06
"""

from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE urls DROP COLUMN IF EXISTS crawl_count")
    op.execute("ALTER TABLE urls DROP COLUMN IF EXISTS last_crawled_at")


def downgrade() -> None:
    pass
