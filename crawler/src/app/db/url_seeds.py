"""URL seed management: mark, unmark, purge, list seeds."""

from app.db.connection import db_connection, db_transaction
from app.db.url_types import url_hash
from shared.postgres.search import sql_placeholder


class UrlSeedsMixin:
    """Mixin for seed URL operations."""

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
        """Delete pending URLs whose domain matches the blocklist.

        Uses subdomain matching: blocking 'facebook.com' also removes
        'www.facebook.com', 'm.facebook.com', etc.

        Returns the number of deleted rows.
        """
        if not blocklist:
            return 0

        with db_transaction(self.db_path) as cur:
            # Build WHERE conditions for each blocked domain
            conditions = []
            params: list[str] = []
            for d in blocklist:
                conditions.append(f"domain = {sql_placeholder()}")
                params.append(d)
                # Escape SQL LIKE wildcards in domain name
                escaped = (
                    d.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                conditions.append(f"domain LIKE {sql_placeholder()} ESCAPE '\\'")
                params.append(f"%.{escaped}")

            where = " OR ".join(conditions)
            cur.execute(
                f"DELETE FROM urls WHERE status = 'pending' AND ({where})",
                params,
            )
            return cur.rowcount

    def get_seeds(self) -> list[dict]:
        """Get all URLs marked as seeds."""
        with db_connection(self.db_path) as cur:
            cur.execute(
                "SELECT url, domain, status, priority, created_at, last_crawled_at"
                " FROM urls WHERE is_seed = TRUE ORDER BY created_at DESC"
            )
            return [
                {
                    "url": row[0],
                    "domain": row[1],
                    "status": row[2],
                    "priority": row[3],
                    "created_at": row[4],
                    "last_crawled_at": row[5],
                }
                for row in cur.fetchall()
            ]
