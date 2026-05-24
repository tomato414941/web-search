"""Persisted crawler admin counters."""

from __future__ import annotations

import time

from web_search_crawler.db.connection import db_connection, db_transaction
from web_search_postgres.search import sql_placeholder

_FRONTIER_ADMIN_ROW_NAME = "frontier"


def _empty_frontier_counters() -> dict[str, int]:
    return {
        "pending_rows": 0,
        "leased_rows": 0,
        "frontier_rows": 0,
    }


class FrontierAdminStateStore:
    """Persisted admin-facing frontier read model."""

    def __init__(self, db_path: str, *, refresh_interval_sec: int = 60):
        self.db_path = db_path
        self._refresh_interval_sec = max(0, refresh_interval_sec)

    def ensure_frontier_counters_row(self, cur, *, now: int) -> None:
        ph = sql_placeholder()
        cur.execute(
            f"""
            INSERT INTO frontier_counters (
                name,
                pending_rows,
                leased_rows,
                frontier_rows,
                updated_at
            )
            VALUES ({ph}, 0, 0, 0, {ph})
            ON CONFLICT (name) DO NOTHING
            """,
            (_FRONTIER_ADMIN_ROW_NAME, now),
        )

    def set_frontier_counters(
        self,
        *,
        pending_rows: int,
        leased_rows: int,
        frontier_rows: int,
        now: int | None = None,
    ) -> dict[str, int]:
        timestamp = int(time.time()) if now is None else now
        with db_transaction(self.db_path) as cur:
            self.ensure_frontier_counters_row(cur, now=timestamp)
            ph = sql_placeholder()
            cur.execute(
                f"""
                UPDATE frontier_counters
                SET
                    pending_rows = {ph},
                    leased_rows = {ph},
                    frontier_rows = {ph},
                    updated_at = {ph}
                WHERE name = {ph}
                """,
                (
                    max(0, pending_rows),
                    max(0, leased_rows),
                    max(0, frontier_rows),
                    timestamp,
                    _FRONTIER_ADMIN_ROW_NAME,
                ),
            )
        return {
            "pending_rows": max(0, pending_rows),
            "leased_rows": max(0, leased_rows),
            "frontier_rows": max(0, frontier_rows),
        }

    def rebuild_frontier_counters(self, *, now: int | None = None) -> dict[str, int]:
        timestamp = int(time.time()) if now is None else now
        with db_transaction(self.db_path) as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending'),
                    COUNT(*) FILTER (WHERE status = 'leased'),
                    COUNT(*)
                FROM frontier_entries
                """
            )
            pending_rows, leased_rows, frontier_rows = cur.fetchone()
            self.ensure_frontier_counters_row(cur, now=timestamp)
            ph = sql_placeholder()
            cur.execute(
                f"""
                UPDATE frontier_counters
                SET
                    pending_rows = {ph},
                    leased_rows = {ph},
                    frontier_rows = {ph},
                    updated_at = {ph}
                WHERE name = {ph}
                """,
                (
                    int(pending_rows or 0),
                    int(leased_rows or 0),
                    int(frontier_rows or 0),
                    timestamp,
                    _FRONTIER_ADMIN_ROW_NAME,
                ),
            )
        return {
            "pending_rows": int(pending_rows or 0),
            "leased_rows": int(leased_rows or 0),
            "frontier_rows": int(frontier_rows or 0),
        }

    def get_frontier_counters(self) -> dict[str, int]:
        current_time = int(time.time())
        if self._refresh_interval_sec == 0:
            return self.rebuild_frontier_counters(now=current_time)
        with db_connection(self.db_path) as cur:
            ph = sql_placeholder()
            cur.execute(
                f"""
                SELECT pending_rows, leased_rows, frontier_rows, updated_at
                FROM frontier_counters
                WHERE name = {ph}
                """,
                (_FRONTIER_ADMIN_ROW_NAME,),
            )
            row = cur.fetchone()
            if row is None:
                return _empty_frontier_counters()
            return {
                "pending_rows": int(row[0] or 0),
                "leased_rows": int(row[1] or 0),
                "frontier_rows": int(row[2] or 0),
            }
