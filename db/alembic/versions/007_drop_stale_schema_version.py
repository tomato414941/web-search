"""Drop stale schema_version table.

Revision ID: 007
Revises: 006
Create Date: 2026-06-08
"""

from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS schema_version CASCADE")


def downgrade() -> None:
    pass
