"""URL maintenance operations."""

import time

from web_search_crawler.db.connection import db_connection, db_transaction
from web_search_postgres.search import sql_placeholder


class UrlMaintenanceMixin:
    """Mixin for URL maintenance operations."""

    db_path: str

    def purge_denied_domains(self, denylist: frozenset[str]) -> int:
        """Delete scheduled crawl tasks whose domain matches the denylist.

        Uses subdomain matching: denying 'facebook.com' also removes
        'www.facebook.com', 'm.facebook.com', etc.

        Returns the number of deleted crawl schedule rows.
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
            crawl_schedule_params = params + [int(time.time())]
            cur.execute(
                f"""
                WITH deleted AS (
                    DELETE FROM crawl_schedule
                    WHERE ({where})
                    RETURNING domain, status
                ),
                leased AS (
                    SELECT domain, COUNT(*) AS leased_count
                    FROM deleted
                    WHERE status = 'leased'
                    GROUP BY domain
                ),
                updated AS (
                    UPDATE domain_state AS ds
                    SET
                        inflight_leases = GREATEST(
                            ds.inflight_leases - leased.leased_count,
                            0
                        ),
                        updated_at = {sql_placeholder()}
                    FROM leased
                    WHERE ds.domain = leased.domain
                    RETURNING 1
                ),
                deleted_count AS (
                    SELECT COUNT(*) AS cnt
                    FROM deleted
                ),
                pending_count AS (
                    SELECT COUNT(*) AS cnt
                    FROM deleted
                    WHERE status = 'pending'
                ),
                leased_count AS (
                    SELECT COUNT(*) AS cnt
                    FROM deleted
                    WHERE status = 'leased'
                )
                SELECT
                    deleted_count.cnt,
                    pending_count.cnt,
                    leased_count.cnt
                FROM deleted_count, pending_count, leased_count
                """,
                crawl_schedule_params,
            )
            crawl_schedule_deleted, pending_deleted, leased_deleted = cur.fetchone()
            crawl_schedule_deleted = int(crawl_schedule_deleted or 0)
            return crawl_schedule_deleted

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
            crawl_schedule_where = ["status IN ('pending', 'leased')"]
            crawl_schedule_params: list[object] = []
            if domain_filter:
                crawl_schedule_where.append(f"domain = ANY({ph})")
                crawl_schedule_params.append(list(domain_filter))
            for row in _select_rows(
                cur,
                table="crawl_schedule",
                columns="url_hash, url, domain, status, discovered_at",
                where=crawl_schedule_where,
                params=crawl_schedule_params,
                order_column="discovered_at",
            ):
                decision = self.url_admission_policy.evaluate(row[1])
                if decision.action == "allow":
                    continue
                candidates.append(
                    {
                        "source": "crawl_schedule",
                        "url_hash": row[0],
                        "url": row[1],
                        "domain": row[2],
                        "status": row[3],
                        "reason_code": decision.reason_code,
                        "created_at": row[4],
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
            "crawl_schedule_deleted": 0,
            "candidates": candidates,
        }
        if dry_run or not candidates:
            return summary

        ph = sql_placeholder()
        crawl_schedule_hashes = [
            row["url_hash"] for row in candidates if row["source"] == "crawl_schedule"
        ]
        leased_domains = [
            row["domain"]
            for row in candidates
            if row["source"] == "crawl_schedule" and row["status"] == "leased"
        ]
        now = int(time.time())

        with db_transaction(self.db_path) as cur:
            if crawl_schedule_hashes:
                cur.execute(
                    f"""
                    SELECT status
                    FROM crawl_schedule
                    WHERE url_hash = ANY({ph})
                    """,
                    (crawl_schedule_hashes,),
                )
                cur.fetchall()
                cur.execute(
                    f"""
                    DELETE FROM crawl_schedule
                    WHERE url_hash = ANY({ph})
                    """,
                    (crawl_schedule_hashes,),
                )
                summary["crawl_schedule_deleted"] = cur.rowcount
            if leased_domains:
                self.domain_scheduling_state.adjust_inflight_leases(
                    cur, leased_domains, delta=-1, now=now
                )

        return summary
