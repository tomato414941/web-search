"""Redesign urls table: discovery ledger + crawl queue.

Split URL management into two tables:
- urls: discovery ledger (all known URLs, url_hash PK, no status/priority)
- crawl_queue: work queue (pending URLs, DELETE on pop)

Removes: status, priority columns.
Retains: url_hash as primary key.

Revision ID: 010
Revises: 009
Create Date: 2026-03-04
"""

from typing import Sequence, Union

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Reset crawling rows before migration
    op.execute("UPDATE urls SET status = 'pending' WHERE status = 'crawling'")

    # Create new urls table (discovery ledger, url_hash PK)
    op.execute("""
        CREATE TABLE urls_new (
            url_hash        TEXT PRIMARY KEY,
            url             TEXT NOT NULL,
            domain          TEXT NOT NULL,
            crawl_count     INTEGER NOT NULL DEFAULT 0,
            created_at      INTEGER NOT NULL,
            last_crawled_at INTEGER,
            is_seed         BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)

    # Migrate done/failed rows (set crawl_count, last_crawled_at)
    op.execute("""
        INSERT INTO urls_new (url_hash, url, domain, crawl_count,
                              created_at, last_crawled_at, is_seed)
        SELECT url_hash, url, domain, crawl_count,
               created_at, COALESCE(last_crawled_at, created_at), is_seed
        FROM urls
        WHERE status IN ('done', 'failed')
    """)

    # Migrate pending rows (crawl_count=0, last_crawled_at=NULL)
    op.execute("""
        INSERT INTO urls_new (url_hash, url, domain, crawl_count,
                              created_at, is_seed)
        SELECT url_hash, url, domain, 0, created_at, is_seed
        FROM urls
        WHERE status = 'pending'
        ON CONFLICT (url_hash) DO NOTHING
    """)

    # Create index on new urls table
    op.execute("CREATE INDEX idx_urls_new_domain ON urls_new(domain)")

    # Create crawl_queue table
    op.execute("""
        CREATE TABLE crawl_queue (
            url_hash   TEXT PRIMARY KEY,
            url        TEXT NOT NULL,
            domain     TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)

    # Populate crawl_queue from pending rows
    op.execute("""
        INSERT INTO crawl_queue (url_hash, url, domain, created_at)
        SELECT url_hash, url, domain, created_at
        FROM urls
        WHERE status = 'pending'
    """)

    # Swap tables
    op.execute("DROP TABLE urls")
    op.execute("ALTER TABLE urls_new RENAME TO urls")
    op.execute("ALTER INDEX idx_urls_new_domain RENAME TO idx_urls_domain")

    # Drop old partial indexes that no longer exist on new table
    # (they were on the old table, already gone with DROP TABLE)


def downgrade() -> None:
    # Recreate original urls table with status/priority
    op.execute("""
        CREATE TABLE urls_old (
            url_hash    TEXT PRIMARY KEY,
            url         TEXT NOT NULL,
            domain      TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending',
            priority    REAL NOT NULL DEFAULT 0,
            crawl_count INTEGER NOT NULL DEFAULT 0,
            created_at  INTEGER NOT NULL,
            last_crawled_at INTEGER,
            is_seed     BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)

    # Migrate crawled URLs back as 'done'
    op.execute("""
        INSERT INTO urls_old (url_hash, url, domain, status, priority,
                              crawl_count, created_at, last_crawled_at, is_seed)
        SELECT url_hash, url, domain, 'done', 0, crawl_count,
               created_at, last_crawled_at, is_seed
        FROM urls
        WHERE last_crawled_at IS NOT NULL
    """)

    # Migrate uncrawled URLs back as 'pending'
    op.execute("""
        INSERT INTO urls_old (url_hash, url, domain, status, priority,
                              crawl_count, created_at, is_seed)
        SELECT url_hash, url, domain, 'pending', 0, 0,
               created_at, is_seed
        FROM urls
        WHERE last_crawled_at IS NULL
        ON CONFLICT (url_hash) DO NOTHING
    """)

    # Recreate original indexes
    op.execute(
        "CREATE INDEX idx_urls_pending_claim "
        "ON urls_old(status, priority DESC, created_at) "
        "WHERE status = 'pending'"
    )
    op.execute(
        "CREATE INDEX idx_urls_pending_domain "
        "ON urls_old(domain) WHERE status = 'pending'"
    )
    op.execute("CREATE INDEX idx_urls_domain_old ON urls_old(domain)")

    # Swap
    op.execute("DROP TABLE crawl_queue")
    op.execute("DROP TABLE urls")
    op.execute("ALTER TABLE urls_old RENAME TO urls")
    op.execute("ALTER INDEX idx_urls_domain_old RENAME TO idx_urls_domain")
