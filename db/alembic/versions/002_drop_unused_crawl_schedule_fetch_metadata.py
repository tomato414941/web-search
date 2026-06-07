"""Drop unused crawl schedule fetch metadata columns.

Revision ID: 002
Revises: 001
Create Date: 2026-06-07
"""

from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE crawl_schedule DROP COLUMN IF EXISTS etag")
    op.execute("ALTER TABLE crawl_schedule DROP COLUMN IF EXISTS last_modified")
    op.execute("ALTER TABLE crawl_schedule DROP COLUMN IF EXISTS content_hash")


def downgrade() -> None:
    pass
