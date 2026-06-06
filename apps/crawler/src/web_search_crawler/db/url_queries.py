"""URL read-only queries: frontier entry inspection."""

from web_search_crawler.services.crawl_policy import POLICIES
from web_search_crawler.db.connection import db_connection
from web_search_crawler.db.url_types import FrontierEntry, url_hash
from web_search_postgres.search import sql_placeholder

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

    def get_frontier_entry(self, url: str) -> FrontierEntry | None:
        """Return frontier metadata for a URL, if present."""
        h = url_hash(url)
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT url, domain, canonical_source, crawl_profile,
                       priority_bucket, priority_score, status, next_fetch_at
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
                canonical_source=row[2],
                crawl_profile=row[3],
                priority_bucket=row[4],
                priority_score=float(row[5]),
                status=row[6],
                next_fetch_at=row[7],
            )
