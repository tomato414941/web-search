"""URL seed management: mark, unmark, get, purge."""

from app.db.connection import db_connection, db_transaction
from app.db.url_types import url_hash
from shared.postgres.search import sql_placeholder


class UrlSeedsMixin:
    """Mixin for seed URL operations."""

    db_path: str

    def mark_seeds(self, urls: list[str]) -> int:
        """Set is_seed = TRUE for the given URLs."""
        if not urls:
            return 0

        ph = sql_placeholder()
        hashes = [url_hash(u) for u in urls]
        with db_transaction(self.db_path) as cur:
            cur.execute(
                f"UPDATE urls SET is_seed = TRUE WHERE url_hash = ANY({ph})",
                (hashes,),
            )
            return cur.rowcount

    def unmark_seeds(self, urls: list[str]) -> int:
        """Set is_seed = FALSE for the given URLs."""
        if not urls:
            return 0

        ph = sql_placeholder()
        hashes = [url_hash(u) for u in urls]
        with db_transaction(self.db_path) as cur:
            cur.execute(
                f"UPDATE urls SET is_seed = FALSE WHERE url_hash = ANY({ph})",
                (hashes,),
            )
            return cur.rowcount

    def purge_blocked_domains(self, blocklist: frozenset[str]) -> int:
        """Delete queued URLs whose domain matches the blocklist.

        Uses subdomain matching: blocking 'facebook.com' also removes
        'www.facebook.com', 'm.facebook.com', etc.

        Returns the number of deleted rows.
        """
        if not blocklist:
            return 0

        with db_transaction(self.db_path) as cur:
            conditions = []
            params: list[str] = []
            for d in blocklist:
                conditions.append(f"domain = {sql_placeholder()}")
                params.append(d)
                escaped = (
                    d.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                conditions.append(f"domain LIKE {sql_placeholder()} ESCAPE '\\'")
                params.append(f"%.{escaped}")

            where = " OR ".join(conditions)
            cur.execute(
                f"DELETE FROM crawl_queue WHERE ({where})",
                params,
            )
            return cur.rowcount

    def count_seeds(self) -> int:
        """Count URLs marked as seeds."""
        with db_connection(self.db_path) as cur:
            cur.execute("SELECT COUNT(*) FROM urls WHERE is_seed = TRUE")
            return cur.fetchone()[0]

    def get_seeds(self, limit: int | None = None, offset: int = 0) -> list[dict]:
        """Get URLs marked as seeds."""
        with db_connection(self.db_path) as cur:
            if limit is None:
                cur.execute(
                    "SELECT url, domain, crawl_count, created_at, last_crawled_at"
                    " FROM urls WHERE is_seed = TRUE ORDER BY created_at DESC"
                )
            else:
                ph = sql_placeholder()
                cur.execute(
                    "SELECT url, domain, crawl_count, created_at, last_crawled_at"
                    " FROM urls WHERE is_seed = TRUE ORDER BY created_at DESC"
                    f" LIMIT {ph} OFFSET {ph}",
                    (limit, max(0, offset)),
                )
            return [
                {
                    "url": row[0],
                    "domain": row[1],
                    "status": "done" if row[2] > 0 else "pending",
                    "created_at": row[3],
                    "last_crawled_at": row[4],
                }
                for row in cur.fetchall()
            ]
