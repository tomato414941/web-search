"""Drop stored URL discovery route columns.

Revision ID: 006
Revises: 005
Create Date: 2026-06-06
"""

from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.crawl_schedule') IS NOT NULL THEN
                UPDATE crawl_schedule
                SET crawl_profile = 'operator_priority'
                WHERE crawl_profile = 'manual_now';
            ELSIF to_regclass('public.frontier_entries') IS NOT NULL THEN
                UPDATE frontier_entries
                SET crawl_profile = 'operator_priority'
                WHERE crawl_profile = 'manual_now';
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE urls DROP COLUMN IF EXISTS discovered_via")
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.crawl_schedule') IS NOT NULL THEN
                ALTER TABLE crawl_schedule DROP COLUMN IF EXISTS discovered_via;
            ELSIF to_regclass('public.frontier_entries') IS NOT NULL THEN
                ALTER TABLE frontier_entries DROP COLUMN IF EXISTS discovered_via;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    pass
