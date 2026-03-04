"""URL read-only queries: counts, stats, domain lookups."""

import time

from app.db.connection import db_connection
from app.db.url_types import UrlItem, url_hash
from shared.postgres.search import sql_placeholder, sql_placeholders


class UrlQueriesMixin:
    """Mixin for URL read-only queries and statistics."""

    db_path: str
    recrawl_threshold: int

    def pending_count(self) -> int:
        """Return number of pending URLs."""
        with db_connection(self.db_path) as cur:
            cur.execute("SELECT COUNT(*) FROM urls WHERE status = 'pending'")
            return cur.fetchone()[0]

    def contains(self, url: str) -> bool:
        """Check if URL exists in any status."""
        h = url_hash(url)
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(f"SELECT 1 FROM urls WHERE url_hash = {ph}", (h,))
            return cur.fetchone() is not None

    def is_recently_crawled(self, url: str) -> bool:
        """
        Check if URL was crawled within recrawl threshold.

        Returns:
            True if recently crawled (should skip)
        """
        h = url_hash(url)
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        ph = sql_placeholder()

        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT 1 FROM urls
                WHERE url_hash = {ph} AND last_crawled_at > {ph}
                """,
                (h, cutoff),
            )
            return cur.fetchone() is not None

    def peek(self, count: int = 10) -> list[UrlItem]:
        """View top pending URLs without modifying them."""
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT url_hash, url, domain, priority, created_at
                FROM urls
                WHERE status = 'pending'
                ORDER BY priority DESC
                LIMIT {ph}
                """,
                (count,),
            )
            return [
                UrlItem(
                    url=row[1],
                    domain=row[2],
                    priority=row[3],
                    created_at=row[4],
                )
                for row in cur.fetchall()
            ]

    def get_stale_urls(self, limit: int = 100) -> list[str]:
        """Get URLs ready for re-crawl (done and past threshold)."""
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        ph = sql_placeholder()

        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT url FROM urls
                WHERE last_crawled_at < {ph} AND status = 'done'
                ORDER BY last_crawled_at ASC
                LIMIT {ph}
                """,
                (cutoff, limit),
            )
            return [row[0] for row in cur.fetchall()]

    def get_stale_url_count(self) -> int:
        """Count URLs ready for re-crawl (done and past threshold)."""
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        ph = sql_placeholder()

        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) FROM urls
                WHERE last_crawled_at < {ph} AND status = 'done'
                """,
                (cutoff,),
            )
            return cur.fetchone()[0]

    def get_stats(self) -> dict:
        """Get URL statistics.

        Uses pg_class/pg_stats for approximate per-status counts when
        available (large tables), falling back to exact COUNT for small
        or freshly-created tables where pg_stats has no data yet.
        """
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        ph = sql_placeholder()

        with db_connection(self.db_path) as cur:
            # Try approximate counts from pg_class + pg_stats
            cur.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = 'urls'")
            row = cur.fetchone()
            total = row[0] if row and row[0] > 0 else 0

            status_counts: dict[str, int] | None = None
            if total > 0:
                cur.execute(
                    "SELECT unnest(most_common_vals::text::text[]) AS status,"
                    " unnest(most_common_freqs) AS freq"
                    " FROM pg_stats"
                    " WHERE tablename = 'urls' AND attname = 'status'"
                )
                rows = cur.fetchall()
                if rows:
                    status_counts = {r[0]: round(total * r[1]) for r in rows}

            if status_counts is not None:
                # Fast path: approximate counts + indexed recent query
                cur.execute(
                    f"SELECT COUNT(*) FROM urls WHERE last_crawled_at > {ph}",
                    (cutoff,),
                )
                recent = cur.fetchone()[0]
                return {
                    "pending": status_counts.get("pending", 0),
                    "crawling": status_counts.get("crawling", 0),
                    "done": status_counts.get("done", 0),
                    "failed": status_counts.get("failed", 0),
                    "total": total,
                    "recent": recent,
                }

            # Fallback: exact counts (small tables / no pg_stats data)
            cur.execute(
                f"""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE status = 'crawling') AS crawling,
                    COUNT(*) FILTER (WHERE status = 'done') AS done,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE last_crawled_at > {ph}) AS recent
                FROM urls
                """,
                (cutoff,),
            )
            row = cur.fetchone()
            return {
                "pending": row[0],
                "crawling": row[1],
                "done": row[2],
                "failed": row[3],
                "total": row[4],
                "recent": row[5],
            }

    def get_domains(self, limit: int = 100) -> list[tuple[str, int]]:
        """Get domain counts for done URLs."""
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT domain, COUNT(*) as cnt
                FROM urls
                WHERE status = 'done'
                GROUP BY domain
                ORDER BY cnt DESC
                LIMIT {ph}
                """,
                (limit,),
            )
            return [(row[0], row[1]) for row in cur.fetchall()]

    def get_pending_domains(self, limit: int = 15) -> list[tuple[str, int]]:
        """Get top domains by pending URL count."""
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT domain, COUNT(*) as cnt
                FROM urls
                WHERE status = 'pending'
                GROUP BY domain
                ORDER BY cnt DESC
                LIMIT {ph}
                """,
                (limit,),
            )
            return [(row[0], row[1]) for row in cur.fetchall()]

    def domain_done_count(self, domain: str) -> int:
        """Return number of 'done' URLs for a given domain."""
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM urls WHERE domain = {ph} AND status = 'done'",
                (domain,),
            )
            return cur.fetchone()[0]

    def domain_done_count_batch(self, domains: list[str]) -> dict[str, int]:
        """Return done-URL counts for multiple domains in a single query."""
        if not domains:
            return {}
        phs = sql_placeholders(len(domains))
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"SELECT domain, COUNT(*) FROM urls "
                f"WHERE domain IN ({phs}) AND status = 'done' "
                f"GROUP BY domain",
                tuple(domains),
            )
            return {row[0]: row[1] for row in cur.fetchall()}

    def size(self) -> int:
        """Return total number of URLs (all statuses). For health checks."""
        with db_connection(self.db_path) as cur:
            cur.execute("SELECT COUNT(*) FROM urls")
            return cur.fetchone()[0]
