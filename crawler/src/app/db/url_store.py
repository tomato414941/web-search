"""
URL Store - Discovery Ledger + Crawl Queue

urls table: ledger of all discovered URLs (no status column).
crawl_queue table: work queue of URLs to crawl next (DELETE on pop).
"""

from app.db.url_discovery import UrlDiscoveryMixin
from app.db.url_queries import UrlQueriesMixin
from app.db.url_queue import UrlQueueMixin
from app.db.url_seeds import UrlSeedsMixin
from shared.postgres.search import get_connection


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS urls (
    url_hash        TEXT PRIMARY KEY,
    url             TEXT NOT NULL,
    domain          TEXT NOT NULL,
    crawl_count     INTEGER NOT NULL DEFAULT 0,
    created_at      INTEGER NOT NULL,
    last_crawled_at INTEGER,
    is_seed         BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_urls_domain ON urls(domain);

CREATE TABLE IF NOT EXISTS crawl_queue (
    url_hash   TEXT PRIMARY KEY,
    url        TEXT NOT NULL,
    domain     TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""


class UrlStore(UrlDiscoveryMixin, UrlQueueMixin, UrlQueriesMixin, UrlSeedsMixin):
    """
    URL storage backed by a discovery ledger (urls) and a crawl queue.

    urls: all discovered URLs. last_crawled_at IS NULL means never crawled.
    crawl_queue: URLs waiting to be crawled. Popped via DELETE.
    """

    def __init__(
        self,
        db_path: str,
        recrawl_after_days: int = 30,
        max_pending_per_domain: int = 0,
    ):
        self.db_path = db_path
        self.recrawl_threshold = recrawl_after_days * 86400
        self.max_pending_per_domain = max_pending_per_domain
        self._init_db()

    def _init_db(self):
        # Schema is managed by Alembic; verify connectivity only.
        con = get_connection(self.db_path)
        con.close()
