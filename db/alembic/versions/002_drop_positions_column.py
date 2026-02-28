"""Drop unused positions column from inverted_index.

The positions column stores JSON arrays of token positions for phrase/proximity
search, but this feature was never implemented. The column is written by
_index_field() but never read by searcher.py or scoring.py.

Dropping it reduces inverted_index size by ~40-60%.

Revision ID: 002
Revises: 001
Create Date: 2026-02-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE inverted_index DROP COLUMN IF EXISTS positions")


def downgrade() -> None:
    op.execute("ALTER TABLE inverted_index ADD COLUMN IF NOT EXISTS positions TEXT")
