"""Drop index_jobs.max_retries.

Revision ID: 015
Revises: 014
Create Date: 2026-06-15
"""

from typing import Sequence, Union

from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE index_jobs DROP COLUMN IF EXISTS max_retries")
