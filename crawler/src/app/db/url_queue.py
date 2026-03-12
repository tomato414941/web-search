"""URL queue operations: pop pending work, requeue, and release denied items."""

import time

from app.db.connection import db_transaction
from app.db.url_types import UrlItem, get_domain, url_hash
from shared.postgres.search import sql_placeholder


class UrlQueueMixin:
    """Mixin for crawl_queue mutations and pending work selection."""

    db_path: str

    def pop_batch(self, count: int, max_per_domain: int = 3) -> list[UrlItem]:
        """
        Pop URLs from the crawl queue.
        Ensures domain diversity by limiting URLs per domain.
        """
        if count <= 0:
            return []

        ph = sql_placeholder()

        with db_transaction(self.db_path) as cur:
            # Fetch a small candidate window cheaply, then apply diversity locally.
            # This avoids a global queue sort, which becomes too expensive at scale.
            overscan = count * max_per_domain * 3
            cur.execute(
                f"""
                WITH candidates AS (
                    SELECT url_hash, url, domain, created_at
                    FROM crawl_queue
                    LIMIT {ph}
                    FOR UPDATE SKIP LOCKED
                ),
                per_domain AS (
                    SELECT url_hash, url, domain, created_at,
                           ROW_NUMBER() OVER (
                               PARTITION BY domain ORDER BY created_at, url_hash
                           ) AS rn
                    FROM candidates
                ),
                selected AS (
                    SELECT url_hash
                    FROM per_domain
                    WHERE rn <= {ph}
                    ORDER BY created_at, url_hash
                    LIMIT {ph}
                )
                DELETE FROM crawl_queue
                USING selected s
                WHERE crawl_queue.url_hash = s.url_hash
                RETURNING crawl_queue.url, crawl_queue.domain, crawl_queue.created_at
                """,
                (overscan, max_per_domain, count),
            )
            rows = cur.fetchall()

            return [
                UrlItem(url=row[0], domain=row[1], created_at=row[2]) for row in rows
            ]

    def requeue(self, url: str) -> bool:
        """Re-add a URL to the crawl queue (e.g. for retry)."""
        h = url_hash(url)
        domain = get_domain(url)
        now = int(time.time())
        ph = sql_placeholder()
        with db_transaction(self.db_path) as cur:
            cur.execute(
                f"""
                INSERT INTO crawl_queue (url_hash, url, domain, created_at)
                VALUES ({ph}, {ph}, {ph}, {ph})
                ON CONFLICT (url_hash) DO NOTHING
                """,
                (h, url, domain, now),
            )
            return cur.rowcount > 0

    def release_urls(self, urls: list[str]) -> int:
        """
        Mark URLs as crawled (permanently failed / blocked).

        Records last_crawled_at so they won't be re-queued until stale.
        Returns count of affected rows.
        """
        if not urls:
            return 0
        ph = sql_placeholder()
        now = int(time.time())
        hashes = [url_hash(u) for u in urls]
        with db_transaction(self.db_path) as cur:
            cur.execute(
                f"""
                UPDATE urls
                SET last_crawled_at = {ph},
                    crawl_count = crawl_count + 1
                WHERE url_hash = ANY({ph})
                """,
                (now, hashes),
            )
            return cur.rowcount
