"""Rename frontier_entries to crawl_schedule.

Revision ID: 007
Revises: 006
Create Date: 2026-06-07
"""

from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.frontier_entries') IS NOT NULL
               AND to_regclass('public.crawl_schedule') IS NULL THEN
                ALTER TABLE frontier_entries RENAME TO crawl_schedule;
            ELSIF to_regclass('public.frontier_entries') IS NOT NULL
                  AND to_regclass('public.crawl_schedule') IS NOT NULL THEN
                RAISE EXCEPTION
                    'both frontier_entries and crawl_schedule exist; refusing ambiguous migration';
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'frontier_entries_pkey'
            ) THEN
                ALTER TABLE crawl_schedule
                RENAME CONSTRAINT frontier_entries_pkey TO crawl_schedule_pkey;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        ALTER INDEX IF EXISTS idx_frontier_ready
        RENAME TO idx_crawl_schedule_ready
        """
    )
    op.execute(
        """
        ALTER INDEX IF EXISTS idx_frontier_domain_ready
        RENAME TO idx_crawl_schedule_domain_ready
        """
    )
    op.execute(
        """
        ALTER INDEX IF EXISTS idx_frontier_profile_ready
        RENAME TO idx_crawl_schedule_profile_ready
        """
    )
    op.execute(
        """
        ALTER INDEX IF EXISTS idx_frontier_pending_planner_order
        RENAME TO idx_crawl_schedule_pending_planner_order
        """
    )
    op.execute(
        """
        ALTER INDEX IF EXISTS idx_frontier_profile_planner_order
        RENAME TO idx_crawl_schedule_profile_planner_order
        """
    )


def downgrade() -> None:
    pass
