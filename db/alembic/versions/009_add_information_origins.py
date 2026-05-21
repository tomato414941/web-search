"""Add information_origins table for AI-agent-optimized ranking.

Replaces PageRank's "popular = good" with "primary source = good".
Classifies documents as spring/river/delta/swamp based on link
direction asymmetry.

Revision ID: 009
Revises: 008
Create Date: 2026-03-03
"""

from typing import Sequence, Union

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS information_origins (
            url TEXT PRIMARY KEY REFERENCES documents(url) ON DELETE CASCADE,
            origin_type TEXT NOT NULL DEFAULT 'river',
            score REAL NOT NULL DEFAULT 0.5,
            inlink_count INTEGER DEFAULT 0,
            outlink_count INTEGER DEFAULT 0
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_info_origins_type "
        "ON information_origins(origin_type)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_info_origins_type")
    op.execute("DROP TABLE IF EXISTS information_origins")
