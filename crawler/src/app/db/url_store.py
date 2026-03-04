"""
URL Store - Unified URL Management

Manages the full URL lifecycle: pending → crawling → done/failed.
Replaces the separate Frontier and History tables.
"""

from app.db.url_lifecycle import UrlLifecycleMixin
from app.db.url_queries import UrlQueriesMixin
from app.db.url_seeds import UrlSeedsMixin
from shared.postgres.search import get_connection


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS urls (
    url_hash TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority REAL NOT NULL DEFAULT 0,
    crawl_count INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    last_crawled_at INTEGER,
    is_seed BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_urls_pending_claim ON urls(status, priority DESC, created_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_urls_pending_domain ON urls(domain) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_urls_domain ON urls(domain);
"""


class UrlStore(UrlLifecycleMixin, UrlQueriesMixin, UrlSeedsMixin):
    """
    Unified URL storage.

    Manages the full lifecycle of URLs:
    - pending: discovered, waiting to be crawled
    - crawling: currently being fetched
    - done: successfully crawled
    - failed: crawl failed
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
