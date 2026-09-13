"""Move link observations to an archive outbox; freeze the legacy graph.

Revision ID: 021
Revises: 020
"""

from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Renaming retains the graph and its indexes without copying the large table.
    # Stop and drain the old crawler before applying this cutover migration.
    op.execute("ALTER TABLE links RENAME TO legacy_links")
    op.execute("""
        CREATE FUNCTION reject_legacy_link_write() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'legacy_links is frozen for R2 export';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER freeze_legacy_links
        BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON legacy_links
        FOR EACH STATEMENT EXECUTE FUNCTION reject_legacy_link_write()
    """)
    op.execute("CREATE SEQUENCE link_observation_revision START 1")
    op.execute("""
        CREATE TABLE link_archive_state (
            singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
            pending_bytes BIGINT NOT NULL DEFAULT 0 CHECK (pending_bytes >= 0),
            legacy_started_at TIMESTAMPTZ,
            legacy_last_src TEXT,
            legacy_pages BIGINT NOT NULL DEFAULT 0,
            legacy_edges BIGINT NOT NULL DEFAULT 0,
            legacy_complete BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)
    op.execute("INSERT INTO link_archive_state (singleton) VALUES (TRUE)")
    op.execute("""
        CREATE TABLE link_archive_batches (
            batch_id UUID PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""
        CREATE TABLE link_outbox (
            revision BIGINT PRIMARY KEY CHECK (revision > 0),
            payload TEXT NOT NULL,
            payload_bytes INTEGER NOT NULL CHECK (payload_bytes > 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            batch_id UUID REFERENCES link_archive_batches(batch_id)
        )
    """)
    op.execute("CREATE INDEX link_outbox_batch ON link_outbox (batch_id, revision)")


def downgrade() -> None:
    raise RuntimeError("Restore the matching database and release to undo R2 cutover")
