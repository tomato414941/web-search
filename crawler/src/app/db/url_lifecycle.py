"""URL lifecycle operations: add, pop, record, release, requeue."""

import logging
import os
import time
from collections.abc import Iterable
from typing import Any

from psycopg2.errors import DeadlockDetected, SerializationFailure
from psycopg2.extras import execute_values

from app.db.connection import db_transaction
from app.db.url_types import UrlItem, get_domain, url_hash
from shared.postgres.search import sql_placeholder

logger = logging.getLogger(__name__)

_ENQUEUE_CHUNK_SIZE = int(os.getenv("CRAWL_ENQUEUE_CHUNK_SIZE", "100"))
_ENQUEUE_RETRY_LIMIT = int(os.getenv("CRAWL_ENQUEUE_RETRY_LIMIT", "2"))
_ENQUEUE_RETRY_BASE_SEC = float(os.getenv("CRAWL_ENQUEUE_RETRY_BASE_SEC", "0.05"))


class UrlLifecycleMixin:
    """Mixin for URL lifecycle: discovery ledger (urls) + crawl queue."""

    @staticmethod
    def _chunked(
        seq: list[dict[str, Any]], size: int
    ) -> Iterable[list[dict[str, Any]]]:
        for i in range(0, len(seq), size):
            yield seq[i : i + size]

    def _normalize_batch_urls(self, urls: list[str]) -> list[dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        for url in urls:
            h = url_hash(url)
            records.setdefault(
                h,
                {
                    "h": h,
                    "url": url,
                    "domain": get_domain(url),
                },
            )
        return sorted(records.values(), key=lambda row: row["h"])

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

    def _insert_urls_batch(
        self, cur: Any, rows: list[dict[str, Any]], now: int
    ) -> None:
        if not rows:
            return
        execute_values(
            cur,
            """
            INSERT INTO urls (url_hash, url, domain, created_at)
            VALUES %s
            ON CONFLICT (url_hash) DO NOTHING
            """,
            [(row["h"], row["url"], row["domain"], now) for row in rows],
        )

    def _get_recently_crawled_hashes(
        self, cur: Any, hashes: list[str], cutoff: int
    ) -> set[str]:
        if not hashes:
            return set()
        ph = sql_placeholder()
        cur.execute(
            f"""
            SELECT url_hash
            FROM urls
            WHERE url_hash = ANY({ph})
              AND last_crawled_at IS NOT NULL
              AND last_crawled_at >= {ph}
            """,
            (hashes, cutoff),
        )
        return {row[0] for row in cur.fetchall()}

    def _insert_crawl_queue_batch(
        self, cur: Any, rows: list[dict[str, Any]], now: int
    ) -> set[str]:
        if not rows:
            return set()
        inserted = execute_values(
            cur,
            """
            INSERT INTO crawl_queue (url_hash, url, domain, created_at)
            VALUES %s
            ON CONFLICT (url_hash) DO NOTHING
            RETURNING url_hash
            """,
            [(row["h"], row["url"], row["domain"], now) for row in rows],
            fetch=True,
        )
        return {row[0] for row in inserted}

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

    def _add_batch_chunk(
        self,
        cur: Any,
        rows: list[dict[str, Any]],
        *,
        now: int,
        cutoff: int,
        cap: int,
        queued: dict[str, int],
        batch_adds: dict[str, int],
    ) -> int:
        self._insert_urls_batch(cur, rows, now)

        recent_hashes = self._get_recently_crawled_hashes(
            cur, [row["h"] for row in rows], cutoff
        )
        enqueue_rows: list[dict[str, Any]] = []
        for row in rows:
            if row["h"] in recent_hashes:
                continue
            if cap > 0:
                current = queued.get(row["domain"], 0) + batch_adds.get(
                    row["domain"], 0
                )
                if current >= cap:
                    continue
            enqueue_rows.append(row)

        inserted_hashes = self._insert_crawl_queue_batch(cur, enqueue_rows, now)
        if not inserted_hashes:
            return 0

        added = 0
        for row in enqueue_rows:
            if row["h"] not in inserted_hashes:
                continue
            added += 1
            if cap > 0:
                batch_adds[row["domain"]] = batch_adds.get(row["domain"], 0) + 1
        return added

    def add(self, url: str) -> bool:
        """
        Discover a URL and enqueue it for crawling if eligible.

        Returns:
            True if added to the queue, False otherwise
        """
        return self.add_batch([url]) > 0

    def add_batch(self, urls: list[str]) -> int:
        """
        Discover and enqueue multiple URLs.
        Respects per-domain queue cap (max_pending_per_domain).

        Returns:
            Number of URLs added to the queue
        """
        if not urls:
            return 0

        rows = self._normalize_batch_urls(urls)
        if not rows:
            return 0

        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        cap = self.max_pending_per_domain
        chunk_size = max(1, _ENQUEUE_CHUNK_SIZE)
        queued: dict[str, int] = {}
        batch_adds: dict[str, int] = {}

        if cap > 0:
            domains = sorted({row["domain"] for row in rows})
            with db_transaction(self.db_path) as cur:
                queued = self._get_queue_counts_batch(cur, domains)

        added = 0
        for chunk in self._chunked(rows, chunk_size):
            for attempt in range(_ENQUEUE_RETRY_LIMIT + 1):
                try:
                    with db_transaction(self.db_path) as cur:
                        added += self._add_batch_chunk(
                            cur,
                            chunk,
                            now=now,
                            cutoff=cutoff,
                            cap=cap,
                            queued=queued,
                            batch_adds=batch_adds,
                        )
                    break
                except (DeadlockDetected, SerializationFailure):
                    if attempt >= _ENQUEUE_RETRY_LIMIT:
                        raise
                    delay = _ENQUEUE_RETRY_BASE_SEC * (attempt + 1)
                    logger.warning(
                        "Retrying enqueue chunk after DB concurrency error "
                        "(attempt %d/%d, chunk=%d, delay=%.2fs)",
                        attempt + 1,
                        _ENQUEUE_RETRY_LIMIT,
                        len(chunk),
                        delay,
                    )
                    time.sleep(delay)

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
