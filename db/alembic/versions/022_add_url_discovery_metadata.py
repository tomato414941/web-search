"""Add discovery metadata to urls ledger.

Revision ID: 022
Revises: 021
Create Date: 2026-05-21
"""

from typing import Sequence, Union

from alembic import op

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE urls ADD COLUMN IF NOT EXISTS discovered_via TEXT "
        "NOT NULL DEFAULT 'unknown'"
    )
    op.execute(
        "UPDATE urls SET discovered_via = 'seed' "
        "WHERE is_seed = TRUE AND discovered_via = 'unknown'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE urls DROP COLUMN IF EXISTS discovered_via")
