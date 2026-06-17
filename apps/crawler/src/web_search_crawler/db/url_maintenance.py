"""URL maintenance operations."""

from web_search_crawler.db.connection import db_transaction
from web_search_postgres.search import sql_placeholder


class UrlMaintenanceMixin:
    """Mixin for URL maintenance operations."""

    db_path: str

    def purge_denied_domains(self, denylist: frozenset[str]) -> int:
        """Delete queued crawl tasks whose domain matches the denylist.

        Uses subdomain matching: denying 'facebook.com' also removes
        'www.facebook.com', 'm.facebook.com', etc.

        Returns the number of deleted crawl queue rows.
        """
        if not denylist:
            return 0
        with db_transaction(self.db_path) as cur:
            conditions = []
            params: list[str] = []
            for d in denylist:
                conditions.append(f"domain = {sql_placeholder()}")
                params.append(d)
                escaped = (
                    d.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                conditions.append(f"domain LIKE {sql_placeholder()} ESCAPE '\\'")
                params.append(f"%.{escaped}")

            where = " OR ".join(conditions)
            cur.execute(
                f"""
                WITH deleted AS (
                    DELETE FROM crawl_queue
                    WHERE {where}
                    RETURNING 1
                )
                SELECT COUNT(*) AS cnt
                FROM deleted
                """,
                params,
            )
            crawl_queue_deleted = cur.fetchone()[0]
            return int(crawl_queue_deleted or 0)
