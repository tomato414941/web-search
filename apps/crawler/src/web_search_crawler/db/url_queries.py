"""URL read-only queries: counts and frontier inspection."""

import os

from web_search_crawler.services.crawl_policy import POLICIES
from web_search_crawler.db.connection import db_connection
from web_search_crawler.db.url_types import FrontierEntry, UrlItem, url_hash
from web_search_postgres.search import sql_placeholder

_APPROX_COUNT_THRESHOLD = int(os.getenv("CRAWL_APPROX_COUNT_THRESHOLD", "100000"))
_BUDGET_TIER_ORDER = ("hot", "reference", "bulk", "operator")
_PROFILES_BY_BUDGET_TIER = {
    tier: tuple(
        sorted(
            policy.name for policy in POLICIES.values() if policy.budget_tier == tier
        )
    )
    for tier in _BUDGET_TIER_ORDER
}


class UrlQueriesMixin:
    """Mixin for URL read-only queries and statistics."""

    db_path: str
    recrawl_threshold: int

    def _approx_table_count(self, cur, table_name: str) -> int | None:
        cur.execute(
            "SELECT reltuples::bigint FROM pg_class WHERE oid = %s::regclass",
            (table_name,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        count = row[0]
        if count is None or count <= 0:
            return None
        return int(count)

    def _table_count(self, cur, table_name: str) -> int:
        approx = self._approx_table_count(cur, table_name)
        if approx is not None and approx >= _APPROX_COUNT_THRESHOLD:
            return approx
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cur.fetchone()[0]

    def pending_count(self) -> int:
        """Return number of pending frontier rows."""
        if hasattr(self, "frontier_admin_state"):
            return int(
                self.frontier_admin_state.get_frontier_counters()["pending_rows"]
            )
        with db_connection(self.db_path) as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM frontier_entries
                WHERE status = 'pending'
                """
            )
            return cur.fetchone()[0]

    def frontier_count(self) -> int:
        """Return number of URLs in the frontier table."""
        if hasattr(self, "frontier_admin_state"):
            return int(
                self.frontier_admin_state.get_frontier_counters()["frontier_rows"]
            )
        with db_connection(self.db_path) as cur:
            return self._table_count(cur, "frontier_entries")

    def contains(self, url: str) -> bool:
        """Check if URL exists in the discovery ledger."""
        h = url_hash(url)
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(f"SELECT 1 FROM urls WHERE url_hash = {ph}", (h,))
            return cur.fetchone() is not None

    def get_frontier_entry(self, url: str) -> FrontierEntry | None:
        """Return frontier metadata for a URL, if present."""
        h = url_hash(url)
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT url, domain, discovered_via, is_seed, canonical_source,
                       crawl_profile, priority_bucket, priority_score, status,
                       next_fetch_at
                FROM frontier_entries
                WHERE url_hash = {ph}
                """,
                (h,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return FrontierEntry(
                url=row[0],
                domain=row[1],
                discovered_via=row[2],
                is_seed=row[3],
                canonical_source=row[4],
                crawl_profile=row[5],
                priority_bucket=row[6],
                priority_score=float(row[7]),
                status=row[8],
                next_fetch_at=row[9],
            )

    def peek(self, count: int = 10) -> list[UrlItem]:
        """View top pending frontier URLs without modifying them."""
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT url, domain, discovered_at
                FROM frontier_entries
                WHERE status = 'pending'
                ORDER BY
                    priority_bucket ASC,
                    priority_score DESC,
                    next_fetch_at ASC,
                    discovered_at ASC,
                    url ASC
                LIMIT {ph}
                """,
                (count,),
            )
            return [
                UrlItem(url=row[0], domain=row[1], created_at=row[2])
                for row in cur.fetchall()
            ]

    def get_stats(self) -> dict:
        """Get URL statistics from ledger and frontier."""
        cached = self._get_cached_stats()
        if cached is not None:
            return cached

        counters = (
            self.frontier_admin_state.get_frontier_counters()
            if hasattr(self, "frontier_admin_state")
            else None
        )
        with db_connection(self.db_path) as cur:
            if counters is None:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE status = 'pending'),
                        COUNT(*) FILTER (WHERE status = 'leased')
                    FROM frontier_entries
                    """
                )
                pending, crawling = cur.fetchone()
            else:
                pending = counters["pending_rows"]
                crawling = counters["leased_rows"]

            # Ledger stats (approximate for large tables)
            total = self._approx_table_count(cur, "urls") or 0

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

            stats = {
                "pending": pending,
                "crawling": crawling,
                "done": crawled,
                "failed": 0,
                "total": total,
            }
            self._set_cached_stats(stats)
            return stats

    def size(self) -> int:
        """Return total number of discovered URLs. For health checks."""
        with db_connection(self.db_path) as cur:
            return self._table_count(cur, "urls")
