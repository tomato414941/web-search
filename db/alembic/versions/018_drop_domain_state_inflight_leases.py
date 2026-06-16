"""Drop domain_state.inflight_leases.

Revision ID: 018
Revises: 017
Create Date: 2026-06-16
"""

from typing import Sequence, Union

from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE domain_state DROP COLUMN IF EXISTS inflight_leases")


def downgrade() -> None:
    pass
