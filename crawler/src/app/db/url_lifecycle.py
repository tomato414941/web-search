"""URL lifecycle operations: add, pop, record, release, requeue."""

import time
from typing import Any

from app.db.connection import db_transaction
from app.db.url_types import UrlItem, get_domain, url_hash
from shared.postgres.search import sql_placeholder


class UrlLifecycleMixin:
    """Mixin for URL lifecycle: discovery ledger (urls) + crawl queue."""

    def _get_queue_counts_batch(self, cur: Any, domains: list[str]) -> dict[str, int]:
        """Get queued URL counts per domain."""
        if not domains:
            return {}
        ph = sql_placeholder()
        cur.execute(
            f"SELECT domain, COUNT(*) FROM crawl_queue "
            f"WHERE domain = ANY({ph}) "
            f"GROUP BY domain",
            (domains,),
        )
        return {row[0]: row[1] for row in cur.fetchall()}

    def _enqueue_url(
        self,
        cur: Any,
        *,
        h: str,
        url: str,
        domain: str,
        now: int,
        cutoff: int,
    ) -> bool:
        """Register URL in ledger and enqueue if eligible.

        Returns True if URL was added to the queue.
        """
        ph = sql_placeholder()

        # Register in discovery ledger
        cur.execute(
            f"""
            INSERT INTO urls (url_hash, url, domain, created_at)
            VALUES ({ph}, {ph}, {ph}, {ph})
            ON CONFLICT (url_hash) DO NOTHING
            """,
            (h, url, domain, now),
        )

        # Check if already in queue
        cur.execute(
            f"SELECT 1 FROM crawl_queue WHERE url_hash = {ph}",
            (h,),
        )
        if cur.fetchone():
            return False

        # Check if recently crawled
        cur.execute(
            f"SELECT last_crawled_at FROM urls WHERE url_hash = {ph}",
            (h,),
        )
        row = cur.fetchone()
        if row and row[0] is not None and row[0] >= cutoff:
            return False

        # Enqueue
        cur.execute(
            f"""
            INSERT INTO crawl_queue (url_hash, url, domain, created_at)
            VALUES ({ph}, {ph}, {ph}, {ph})
            ON CONFLICT (url_hash) DO NOTHING
            """,
            (h, url, domain, now),
        )
        return cur.rowcount > 0

    def add(self, url: str) -> bool:
        """
        Discover a URL and enqueue it for crawling if eligible.

        Returns:
            True if added to the queue, False otherwise
        """
        h = url_hash(url)
        domain = get_domain(url)
        now = int(time.time())
        cutoff = now - self.recrawl_threshold

        with db_transaction(self.db_path) as cur:
            return self._enqueue_url(
                cur, h=h, url=url, domain=domain, now=now, cutoff=cutoff
            )

    def add_batch(self, urls: list[str]) -> int:
        """
        Discover and enqueue multiple URLs.
        Respects per-domain queue cap (max_pending_per_domain).

        Returns:
            Number of URLs added to the queue
        """
        if not urls:
            return 0

        added = 0
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        cap = self.max_pending_per_domain

        with db_transaction(self.db_path) as cur:
            queued: dict[str, int] = {}
            if cap > 0:
                domains = list({get_domain(u) for u in urls})
                queued = self._get_queue_counts_batch(cur, domains)
            batch_adds: dict[str, int] = {}

            for url in urls:
                h = url_hash(url)
                domain = get_domain(url)
                if cap > 0:
                    current = queued.get(domain, 0) + batch_adds.get(domain, 0)
                    if current >= cap:
                        continue
                if self._enqueue_url(
                    cur, h=h, url=url, domain=domain, now=now, cutoff=cutoff
                ):
                    added += 1
                    if cap > 0:
                        batch_adds[domain] = batch_adds.get(domain, 0) + 1

            return added

    def pop_batch(self, count: int, max_per_domain: int = 3) -> list[UrlItem]:
        """
        Pop URLs from the crawl queue.
        Ensures domain diversity by limiting URLs per domain.

        Args:
            count: Maximum number of URLs to return
            max_per_domain: Maximum URLs from a single domain

        Returns:
            List of UrlItems (removed from queue)
        """
        if count <= 0:
            return []

        ph = sql_placeholder()

        with db_transaction(self.db_path) as cur:
            # Overscan then filter by domain diversity
            overscan = count * max_per_domain * 3
            cur.execute(
                f"""
                WITH candidates AS (
                    SELECT url_hash, url, domain, created_at
                    FROM crawl_queue
                    ORDER BY created_at
                    LIMIT {ph}
                    FOR UPDATE SKIP LOCKED
                ),
                per_domain AS (
                    SELECT url_hash, url, domain, created_at,
                           ROW_NUMBER() OVER (
                               PARTITION BY domain ORDER BY created_at
                           ) AS rn
                    FROM candidates
                ),
                selected AS (
                    SELECT url_hash
                    FROM per_domain
                    WHERE rn <= {ph}
                    ORDER BY created_at
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
        """Re-add a URL to the crawl queue (e.g. for retry).

        Returns True if inserted, False if already in queue.
        """
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
        """Mark URLs as crawled (permanently failed / blocked).

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

    def record(self, url: str, status: str = "done") -> None:
        """
        Record a crawl result. Updates last_crawled_at and crawl_count.

        Args:
            url: Crawled URL
            status: 'done' or 'failed' (kept for API compat, both update the ledger)
        """
        h = url_hash(url)
        domain = get_domain(url)
        now = int(time.time())
        ph = sql_placeholder()

        with db_transaction(self.db_path) as cur:
            cur.execute(
                f"""
                INSERT INTO urls (url_hash, url, domain, crawl_count, created_at, last_crawled_at)
                VALUES ({ph}, {ph}, {ph}, 1, {ph}, {ph})
                ON CONFLICT (url_hash) DO UPDATE SET
                    last_crawled_at = EXCLUDED.last_crawled_at,
                    crawl_count = urls.crawl_count + 1
                """,
                (h, url, domain, now, now),
            )
