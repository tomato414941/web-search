"""Drop crawl_schedule table.

Revision ID: 019
Revises: 018
Create Date: 2026-06-16
"""

from typing import Sequence, Union

from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS crawl_schedule CASCADE")


def downgrade() -> None:
    pass
