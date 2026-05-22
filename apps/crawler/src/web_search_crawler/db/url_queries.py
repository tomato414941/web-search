"""URL read-only queries: counts, stats, domain lookups."""

import ast
import os
import time

from web_search_crawler.services.crawl_policy import POLICIES
from web_search_crawler.db.connection import db_connection
from web_search_crawler.db.url_types import FrontierEntry, UrlItem, url_hash
from web_search_postgres.search import sql_placeholder, sql_placeholders

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


def _parse_histogram_bounds(value: object) -> list[float]:
    """Parse pg_stats histogram bounds into a sorted float list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [float(item) for item in value]
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return []
        if normalized.startswith("{") and normalized.endswith("}"):
            normalized = "[" + normalized[1:-1] + "]"
        parsed = ast.literal_eval(normalized)
        if isinstance(parsed, (list, tuple)):
            return [float(item) for item in parsed]
    return []


def _estimate_tail_ratio_from_histogram(
    bounds: list[float], cutoff: int
) -> float | None:
    """Estimate the fraction of rows above cutoff from pg_stats histogram bounds."""
    if len(bounds) < 2:
        return None
    if cutoff < bounds[0]:
        return 1.0
    if cutoff >= bounds[-1]:
        return 0.0

    bins = len(bounds) - 1
    for index, (lo, hi) in enumerate(zip(bounds, bounds[1:], strict=False)):
        if cutoff >= hi:
            continue
        tail_bins = bins - index - 1
        if hi <= lo:
            in_bin_ratio = 1.0
        else:
            in_bin_ratio = max(0.0, min(1.0, (hi - cutoff) / (hi - lo)))
        return (tail_bins + in_bin_ratio) / bins
    return 0.0


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

    def _approx_recent_crawled_count(
        self,
        cur,
        *,
        total: int,
        crawled: int,
        cutoff: int,
    ) -> int | None:
        cur.execute(
            """
            SELECT null_frac, histogram_bounds
            FROM pg_stats
            WHERE schemaname = 'public'
              AND tablename = 'urls'
              AND attname = 'last_crawled_at'
            """
        )
        row = cur.fetchone()
        if row is None:
            return None

        null_frac = float(row[0] or 0.0)
        bounds = _parse_histogram_bounds(row[1])
        tail_ratio = _estimate_tail_ratio_from_histogram(bounds, cutoff)
        if tail_ratio is None:
            return None

        non_null_ratio = max(0.0, min(1.0, 1.0 - null_frac))
        estimated = round(total * non_null_ratio * tail_ratio)
        return max(0, min(crawled, estimated))

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
        now = int(time.time())
        cutoff = now - self.recrawl_threshold

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

            if total > 100000:
                recent = self._approx_recent_crawled_count(
                    cur,
                    total=total,
                    crawled=crawled,
                    cutoff=cutoff,
                )
                if recent is None:
                    recent = crawled
            else:
                ph = sql_placeholder()
                cur.execute(
                    f"SELECT COUNT(*) FROM urls WHERE last_crawled_at > {ph}",
                    (cutoff,),
                )
                recent = cur.fetchone()[0]

            stats = {
                "pending": pending,
                "crawling": crawling,
                "done": crawled,
                "failed": 0,
                "total": total,
                "recent": recent,
            }
            self._set_cached_stats(stats)
            return stats

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
            return self._table_count(cur, "urls")
