"""URL lifecycle operations: add, pop, record, release, recover."""

import time
from typing import Any

from app.db.connection import db_transaction
from app.db.url_types import UrlItem, get_domain, url_hash
from shared.postgres.search import sql_placeholder


class UrlLifecycleMixin:
    """Mixin for URL lifecycle state transitions."""

    def _get_pending_counts_batch(self, cur: Any, domains: list[str]) -> dict[str, int]:
        """Get pending URL counts per domain in a single query."""
        if not domains:
            return {}
        ph = sql_placeholder()
        cur.execute(
            f"SELECT domain, COUNT(*) FROM urls "
            f"WHERE domain = ANY({ph}) AND status = 'pending' "
            f"GROUP BY domain",
            (domains,),
        )
        return {row[0]: row[1] for row in cur.fetchall()}

    def _upsert_pending_url(
        self,
        cur: Any,
        *,
        url_hash_value: str,
        url: str,
        domain: str,
        priority: float,
        now: int,
        cutoff: int,
    ) -> bool:
        ph = sql_placeholder()
        cur.execute(
            f"""
            INSERT INTO urls (url_hash, url, domain, status, priority, crawl_count, created_at)
            VALUES ({ph}, {ph}, {ph}, 'pending', {ph}, 0, {ph})
            ON CONFLICT (url_hash) DO UPDATE SET
                status = 'pending',
                priority = EXCLUDED.priority
            WHERE urls.status IN ('done', 'failed') AND urls.last_crawled_at < {ph}
            """,
            (url_hash_value, url, domain, priority, now, cutoff),
        )
        return cur.rowcount > 0

    def _pop_pending_rows(
        self,
        cur: Any,
        *,
        count: int,
        max_per_domain: int,
    ) -> list[tuple[Any, ...]]:
        ph = sql_placeholder()

        # Overscan to ensure enough domain diversity after per-domain cap
        overscan = count * max_per_domain * 3
        cur.execute(
            f"""
            WITH top_candidates AS (
                SELECT url_hash, url, domain, priority, created_at,
                       priority + LEAST(20.0,
                           (EXTRACT(EPOCH FROM NOW())::BIGINT - created_at)
                           / 86400.0 * 0.5
                       ) AS eff_pri
                FROM urls
                WHERE status = 'pending'
                ORDER BY priority DESC
                LIMIT {ph}
                FOR UPDATE SKIP LOCKED
            ),
            per_domain AS (
                SELECT url_hash, url, domain, priority, created_at, eff_pri,
                       ROW_NUMBER() OVER (
                           PARTITION BY domain ORDER BY eff_pri DESC
                       ) AS rn
                FROM top_candidates
            ),
            selected AS (
                SELECT url_hash
                FROM per_domain
                WHERE rn <= {ph}
                ORDER BY eff_pri DESC
                LIMIT {ph}
            )
            UPDATE urls
            SET status = 'crawling'
            FROM selected s
            WHERE urls.url_hash = s.url_hash
            RETURNING urls.url_hash, urls.url, urls.domain,
                      urls.priority, urls.created_at
            """,
            (overscan, max_per_domain, count),
        )
        return cur.fetchall()

    def add(
        self,
        url: str,
        priority: float = 0.0,
    ) -> bool:
        """
        Add a URL as pending. Skips if already pending/crawling.
        Re-adds if done/failed and past recrawl threshold.

        Returns:
            True if added/re-queued, False otherwise
        """
        h = url_hash(url)
        domain = get_domain(url)
        now = int(time.time())
        cutoff = now - self.recrawl_threshold

        with db_transaction(self.db_path) as cur:
            return self._upsert_pending_url(
                cur,
                url_hash_value=h,
                url=url,
                domain=domain,
                priority=priority,
                now=now,
                cutoff=cutoff,
            )

    def add_batch(
        self,
        urls: list[str],
        priority: float = 0.0,
    ) -> int:
        """
        Add multiple URLs as pending.
        Respects per-domain pending cap (max_pending_per_domain).

        Returns:
            Number of URLs added
        """
        if not urls:
            return 0

        added = 0
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        cap = self.max_pending_per_domain

        with db_transaction(self.db_path) as cur:
            pending: dict[str, int] = {}
            if cap > 0:
                domains = list({get_domain(u) for u in urls})
                pending = self._get_pending_counts_batch(cur, domains)
            batch_adds: dict[str, int] = {}

            for url in urls:
                h = url_hash(url)
                domain = get_domain(url)
                if cap > 0:
                    current = pending.get(domain, 0) + batch_adds.get(domain, 0)
                    if current >= cap:
                        continue
                if self._upsert_pending_url(
                    cur,
                    url_hash_value=h,
                    url=url,
                    domain=domain,
                    priority=priority,
                    now=now,
                    cutoff=cutoff,
                ):
                    added += 1
                    if cap > 0:
                        batch_adds[domain] = batch_adds.get(domain, 0) + 1

            return added

    def add_batch_scored(
        self,
        items: list[tuple[str, float]],
    ) -> int:
        """
        Add multiple (url, priority) pairs as pending in a single transaction.
        Respects per-domain pending cap (max_pending_per_domain).

        Returns:
            Number of URLs added
        """
        if not items:
            return 0

        added = 0
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        cap = self.max_pending_per_domain

        with db_transaction(self.db_path) as cur:
            pending: dict[str, int] = {}
            if cap > 0:
                domains = list({get_domain(url) for url, _ in items})
                pending = self._get_pending_counts_batch(cur, domains)
            batch_adds: dict[str, int] = {}

            for url, priority in items:
                h = url_hash(url)
                domain = get_domain(url)
                if cap > 0:
                    current = pending.get(domain, 0) + batch_adds.get(domain, 0)
                    if current >= cap:
                        continue
                if self._upsert_pending_url(
                    cur,
                    url_hash_value=h,
                    url=url,
                    domain=domain,
                    priority=priority,
                    now=now,
                    cutoff=cutoff,
                ):
                    added += 1
                    if cap > 0:
                        batch_adds[domain] = batch_adds.get(domain, 0) + 1
            return added

    def pop_batch(self, count: int, max_per_domain: int = 3) -> list[UrlItem]:
        """
        Get pending URLs and mark them as crawling.
        Ensures domain diversity by limiting URLs per domain.

        Args:
            count: Maximum number of URLs to return
            max_per_domain: Maximum URLs from a single domain

        Returns:
            List of UrlItems
        """
        if count <= 0:
            return []

        with db_transaction(self.db_path) as cur:
            rows = self._pop_pending_rows(
                cur,
                count=count,
                max_per_domain=max_per_domain,
            )

            return [
                UrlItem(
                    url=row[1],
                    domain=row[2],
                    priority=row[3],
                    created_at=row[4],
                )
                for row in rows
            ]

    def requeue_for_retry(self, url: str, priority: float) -> bool:
        """Move a URL from crawling back to pending for retry.

        Only transitions crawling -> pending. Returns True if transitioned.
        """
        h = url_hash(url)
        ph = sql_placeholder()
        with db_transaction(self.db_path) as cur:
            cur.execute(
                f"""
                UPDATE urls
                SET status = 'pending', priority = {ph}
                WHERE url_hash = {ph} AND status = 'crawling'
                """,
                (priority, h),
            )
            return cur.rowcount > 0

    def release_urls(self, urls: list[str], status: str = "failed") -> int:
        """Release URLs from crawling to another status.

        Used to release blocked URLs that were popped from the queue
        but filtered out by the scheduler. Only transitions crawling -> target status.
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
                SET status = {ph}, last_crawled_at = {ph}
                WHERE url_hash = ANY({ph}) AND status = 'crawling'
                """,
                (status, now, hashes),
            )
            return cur.rowcount

    def record(self, url: str, status: str = "done") -> None:
        """
        Record a crawl result. Updates status, last_crawled_at, crawl_count.

        Args:
            url: Crawled URL
            status: 'done' or 'failed'
        """
        h = url_hash(url)
        domain = get_domain(url)
        now = int(time.time())
        ph = sql_placeholder()

        with db_transaction(self.db_path) as cur:
            cur.execute(
                f"""
                INSERT INTO urls (url_hash, url, domain, status, priority, crawl_count, created_at, last_crawled_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, 0, 1, {ph}, {ph})
                ON CONFLICT (url_hash) DO UPDATE SET
                    status = EXCLUDED.status,
                    last_crawled_at = EXCLUDED.last_crawled_at,
                    crawl_count = urls.crawl_count + 1
                """,
                (h, url, domain, status, now, now),
            )

    def recover_stale_crawling(self) -> int:
        """
        Reset stale 'crawling' URLs back to 'pending'.
        Called at startup to recover from crashes.

        Returns:
            Number of URLs recovered
        """
        with db_transaction(self.db_path) as cur:
            cur.execute("UPDATE urls SET status = 'pending' WHERE status = 'crawling'")
            return cur.rowcount
