"""URL seed management: mark, unmark, get, purge."""

import time

from web_search_crawler.db.connection import db_connection, db_transaction
from web_search_crawler.db.url_types import url_hash
from web_search_postgres.search import sql_placeholder


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

    def purge_denied_domains(self, denylist: frozenset[str]) -> int:
        """Delete frontier URLs whose domain matches the denylist.

        Uses subdomain matching: denying 'facebook.com' also removes
        'www.facebook.com', 'm.facebook.com', etc.

        Returns the number of deleted frontier rows.
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
            frontier_params = params + [int(time.time())]
            cur.execute(
                f"""
                WITH deleted AS (
                    DELETE FROM frontier_entries
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
                frontier_params,
            )
            frontier_deleted, pending_deleted, leased_deleted = cur.fetchone()
            frontier_deleted = int(frontier_deleted or 0)
            return frontier_deleted

    def collect_admission_rejected_urls(
        self,
        *,
        limit: int = 100,
        domains: tuple[str, ...] = (),
    ) -> list[dict]:
        """Collect frontier URLs rejected by the current admission policy."""
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
            frontier_where = ["status IN ('pending', 'leased')"]
            frontier_params: list[object] = []
            if domain_filter:
                frontier_where.append(f"domain = ANY({ph})")
                frontier_params.append(list(domain_filter))
            for row in _select_rows(
                cur,
                table="frontier_entries",
                columns="url_hash, url, domain, status, discovered_at",
                where=frontier_where,
                params=frontier_params,
                order_column="discovered_at",
            ):
                decision = self.url_admission_policy.evaluate(row[1])
                if decision.action == "allow":
                    continue
                candidates.append(
                    {
                        "source": "frontier",
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
            "frontier_deleted": 0,
            "candidates": candidates,
        }
        if dry_run or not candidates:
            return summary

        ph = sql_placeholder()
        frontier_hashes = [
            row["url_hash"] for row in candidates if row["source"] == "frontier"
        ]
        leased_domains = [
            row["domain"]
            for row in candidates
            if row["source"] == "frontier" and row["status"] == "leased"
        ]
        now = int(time.time())

        with db_transaction(self.db_path) as cur:
            if frontier_hashes:
                cur.execute(
                    f"""
                    SELECT status
                    FROM frontier_entries
                    WHERE url_hash = ANY({ph})
                    """,
                    (frontier_hashes,),
                )
                cur.fetchall()
                cur.execute(
                    f"""
                    DELETE FROM frontier_entries
                    WHERE url_hash = ANY({ph})
                    """,
                    (frontier_hashes,),
                )
                summary["frontier_deleted"] = cur.rowcount
            if leased_domains:
                self.domain_scheduling_state.adjust_inflight_leases(
                    cur, leased_domains, delta=-1, now=now
                )

        return summary

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
                    "SELECT url, created_at"
                    " FROM urls WHERE is_seed = TRUE ORDER BY created_at DESC"
                )
            else:
                ph = sql_placeholder()
                cur.execute(
                    "SELECT url, created_at"
                    " FROM urls WHERE is_seed = TRUE ORDER BY created_at DESC"
                    f" LIMIT {ph} OFFSET {ph}",
                    (limit, max(0, offset)),
                )
            return [
                {
                    "url": row[0],
                    "created_at": row[1],
                }
                for row in cur.fetchall()
            ]
