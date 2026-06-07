"""Drop persistent seed URL state.

Revision ID: 004
Revises: 003
Create Date: 2026-06-06
"""

from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_urls_seed_created_at")
    op.execute("ALTER TABLE urls DROP COLUMN IF EXISTS is_seed")
    op.execute("ALTER TABLE crawl_schedule DROP COLUMN IF EXISTS is_seed")


def downgrade() -> None:
    pass
