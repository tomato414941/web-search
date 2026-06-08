"""Drop stale information_origins table.

Revision ID: 006
Revises: 005
Create Date: 2026-06-08
"""

from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS information_origins CASCADE")


def downgrade() -> None:
    pass
