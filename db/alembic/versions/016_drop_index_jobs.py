"""Drop index_jobs queue table.

Revision ID: 016
Revises: 015
Create Date: 2026-06-15
"""

from typing import Sequence, Union

from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS index_jobs CASCADE")
