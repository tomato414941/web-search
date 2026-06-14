"""Replace index job dedupe key with active URL uniqueness.

Revision ID: 013
Revises: 012
Create Date: 2026-06-14
"""

from alembic import op


revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        WITH ranked AS (
            SELECT
                job_id,
                ROW_NUMBER() OVER (
                    PARTITION BY url
                    ORDER BY created_at ASC, job_id ASC
                ) AS row_num
            FROM index_jobs
            WHERE status IN ('pending', 'processing', 'failed_retry')
        )
        DELETE FROM index_jobs
        USING ranked
        WHERE index_jobs.job_id = ranked.job_id
          AND ranked.row_num > 1
    """)
    op.execute(
        "ALTER TABLE index_jobs DROP CONSTRAINT IF EXISTS index_jobs_dedupe_key_key"
    )
    op.execute("ALTER TABLE index_jobs DROP COLUMN IF EXISTS dedupe_key")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_index_jobs_active_url
        ON index_jobs(url)
        WHERE status IN ('pending', 'processing', 'failed_retry')
    """)


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported")
