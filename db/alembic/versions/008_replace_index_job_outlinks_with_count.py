"""Replace index job outlinks payloads with a count.

Revision ID: 008
Revises: 007
Create Date: 2026-06-09
"""

from alembic import op


revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE index_jobs
        ADD COLUMN IF NOT EXISTS outlinks_count INTEGER NOT NULL DEFAULT 0
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'index_jobs'
                  AND column_name = 'outlinks'
            ) THEN
                UPDATE index_jobs
                SET outlinks_count = CASE
                    WHEN jsonb_typeof(outlinks) = 'array' THEN jsonb_array_length(outlinks)
                    ELSE 0
                END
                WHERE outlinks IS NOT NULL;

                ALTER TABLE index_jobs DROP COLUMN outlinks;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported")
