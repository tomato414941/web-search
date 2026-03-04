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
        """Return number of URLs in the crawl queue."""
        with db_connection(self.db_path) as cur:
            cur.execute("SELECT COUNT(*) FROM crawl_queue")
            return cur.fetchone()[0]

    def contains(self, url: str) -> bool:
        """Check if URL exists in the discovery ledger."""
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
        """View top queued URLs without modifying them."""
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT url, domain, created_at
                FROM crawl_queue
                ORDER BY created_at
                LIMIT {ph}
                """,
                (count,),
            )
            return [
                UrlItem(url=row[0], domain=row[1], created_at=row[2])
                for row in cur.fetchall()
            ]

    def get_stale_urls(self, limit: int = 100) -> list[str]:
        """Get URLs ready for re-crawl (crawled and past threshold)."""
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        ph = sql_placeholder()

        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT url FROM urls
                WHERE last_crawled_at < {ph} AND last_crawled_at IS NOT NULL
                ORDER BY last_crawled_at ASC
                LIMIT {ph}
                """,
                (cutoff, limit),
            )
            return [row[0] for row in cur.fetchall()]

    def get_stale_url_count(self) -> int:
        """Count URLs ready for re-crawl."""
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        ph = sql_placeholder()

        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) FROM urls
                WHERE last_crawled_at < {ph} AND last_crawled_at IS NOT NULL
                """,
                (cutoff,),
            )
            return cur.fetchone()[0]

    def get_stats(self) -> dict:
        """Get URL statistics from both ledger and queue."""
        now = int(time.time())
        cutoff = now - self.recrawl_threshold

        with db_connection(self.db_path) as cur:
            # Queue count (small table, exact)
            cur.execute("SELECT COUNT(*) FROM crawl_queue")
            pending = cur.fetchone()[0]

            # Ledger stats (approximate for large tables)
            cur.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = 'urls'")
            row = cur.fetchone()
            total = row[0] if row and row[0] > 0 else 0

            if total > 100000:
                # Approximate: use pg_stats for null fraction of last_crawled_at
                cur.execute(
                    "SELECT null_frac FROM pg_stats "
                    "WHERE tablename = 'urls' AND attname = 'last_crawled_at'"
                )
                row = cur.fetchone()
                null_frac = row[0] if row else 0
                uncrawled = round(total * null_frac)
                crawled = total - uncrawled
            else:
                cur.execute("""
                    SELECT
                        COUNT(*) FILTER (WHERE last_crawled_at IS NOT NULL),
                        COUNT(*) FILTER (WHERE last_crawled_at IS NULL)
                    FROM urls
                """)
                row = cur.fetchone()
                crawled = row[0]
                uncrawled = row[1]
                total = crawled + uncrawled

            ph = sql_placeholder()
            cur.execute(
                f"SELECT COUNT(*) FROM urls WHERE last_crawled_at > {ph}",
                (cutoff,),
            )
            recent = cur.fetchone()[0]

            return {
                "pending": pending,
                "crawling": 0,
                "done": crawled,
                "failed": 0,
                "total": total,
                "recent": recent,
            }

    def get_domains(self, limit: int = 100) -> list[tuple[str, int]]:
        """Get domain counts for crawled URLs."""
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT domain, COUNT(*) as cnt
                FROM urls
                WHERE last_crawled_at IS NOT NULL
                GROUP BY domain
                ORDER BY cnt DESC
                LIMIT {ph}
                """,
                (limit,),
            )
            return [(row[0], row[1]) for row in cur.fetchall()]

    def get_pending_domains(self, limit: int = 15) -> list[tuple[str, int]]:
        """Get top domains by queued URL count."""
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT domain, COUNT(*) as cnt
                FROM crawl_queue
                GROUP BY domain
                ORDER BY cnt DESC
                LIMIT {ph}
                """,
                (limit,),
            )
            return [(row[0], row[1]) for row in cur.fetchall()]

    def domain_done_count(self, domain: str) -> int:
        """Return number of crawled URLs for a given domain."""
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM urls "
                f"WHERE domain = {ph} AND last_crawled_at IS NOT NULL",
                (domain,),
            )
            return cur.fetchone()[0]

    def domain_done_count_batch(self, domains: list[str]) -> dict[str, int]:
        """Return crawled-URL counts for multiple domains in a single query."""
        if not domains:
            return {}
        phs = sql_placeholders(len(domains))
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"SELECT domain, COUNT(*) FROM urls "
                f"WHERE domain IN ({phs}) AND last_crawled_at IS NOT NULL "
                f"GROUP BY domain",
                tuple(domains),
            )
            return {row[0]: row[1] for row in cur.fetchall()}

    def size(self) -> int:
        """Return total number of discovered URLs. For health checks."""
        with db_connection(self.db_path) as cur:
            cur.execute("SELECT COUNT(*) FROM urls")
            return cur.fetchone()[0]
