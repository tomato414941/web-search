"""URL maintenance operations."""

from web_search_crawler.db.connection import db_connection, db_transaction
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
                conditions.append(f"u.domain = {sql_placeholder()}")
                params.append(d)
                escaped = (
                    d.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                conditions.append(f"u.domain LIKE {sql_placeholder()} ESCAPE '\\'")
                params.append(f"%.{escaped}")

            where = " OR ".join(conditions)
            cur.execute(
                f"""
                WITH deleted AS (
                    DELETE FROM crawl_queue AS q
                    USING urls AS u
                    WHERE q.url_hash = u.url_hash
                      AND ({where})
                    RETURNING 1
                )
                SELECT COUNT(*) AS cnt
                FROM deleted
                """,
                params,
            )
            crawl_queue_deleted = cur.fetchone()[0]
            return int(crawl_queue_deleted or 0)

    def collect_admission_rejected_urls(
        self,
        *,
        limit: int = 100,
        domains: tuple[str, ...] = (),
    ) -> list[dict]:
        """Collect scheduled crawl URLs rejected by the current admission policy."""
        if limit <= 0:
            return []

        domain_filter = tuple(sorted({domain for domain in domains if domain}))
        candidates: list[dict] = []
        ph = sql_placeholder()

        def _select_rows(
            cur,
            *,
            table: str,
            columns: str,
            where: list[str],
            params: list,
            order_column: str,
        ):
            cur.execute(
                f"""
                SELECT {columns}
                FROM {table}
                WHERE {" AND ".join(where)}
                ORDER BY {order_column} DESC
                LIMIT {ph}
                """,
                params + [limit],
            )
            return cur.fetchall()

        with db_connection(self.db_path) as cur:
            crawl_queue_where = ["TRUE"]
            crawl_queue_params: list[object] = []
            if domain_filter:
                crawl_queue_where.append(f"u.domain = ANY({ph})")
                crawl_queue_params.append(list(domain_filter))
            for row in _select_rows(
                cur,
                table="crawl_queue AS q JOIN urls AS u ON u.url_hash = q.url_hash",
                columns="q.url_hash, u.url, u.domain, q.created_at",
                where=crawl_queue_where,
                params=crawl_queue_params,
                order_column="q.created_at",
            ):
                decision = self.url_admission_policy.evaluate(row[1])
                if decision.action == "allow":
                    continue
                candidates.append(
                    {
                        "source": "crawl_queue",
                        "url_hash": row[0],
                        "url": row[1],
                        "domain": row[2],
                        "reason_code": decision.reason_code,
                        "created_at": row[3],
                    }
                )

        return candidates

    def purge_admission_rejected_urls(
        self,
        *,
        limit: int = 100,
        domains: tuple[str, ...] = (),
        dry_run: bool = False,
    ) -> dict[str, object]:
        """Delete URLs that would now be rejected by the admission policy."""
        candidates = self.collect_admission_rejected_urls(
            limit=limit,
            domains=domains,
        )
        summary = {
            "matched": len(candidates),
            "crawl_queue_deleted": 0,
            "candidates": candidates,
        }
        if dry_run or not candidates:
            return summary

        ph = sql_placeholder()
        crawl_queue_hashes = [
            row["url_hash"] for row in candidates if row["source"] == "crawl_queue"
        ]

        with db_transaction(self.db_path) as cur:
            if crawl_queue_hashes:
                cur.execute(
                    f"""
                    DELETE FROM crawl_queue
                    WHERE url_hash = ANY({ph})
                    """,
                    (crawl_queue_hashes,),
                )
                summary["crawl_queue_deleted"] = cur.rowcount

        return summary
