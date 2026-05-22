"""Persisted crawler admin counters and snapshots."""

from __future__ import annotations

import json
import time
from typing import Any

from psycopg2.extras import Json

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

    @staticmethod
    def _decode_snapshot_json(value: object) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            loaded = json.loads(value)
            if isinstance(loaded, dict):
                return loaded
        return {}

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

    def ensure_frontier_snapshot_row(self, cur, *, now: int) -> None:
        ph = sql_placeholder()
        cur.execute(
            f"""
            INSERT INTO frontier_snapshot (
                name,
                generated_at,
                snapshot_json,
                last_error,
                updated_at
            )
            VALUES ({ph}, NULL, {ph}::jsonb, NULL, {ph})
            ON CONFLICT (name) DO NOTHING
            """,
            (_FRONTIER_ADMIN_ROW_NAME, "{}", now),
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

    def get_live_leased_rows(self) -> int:
        with db_connection(self.db_path) as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM frontier_entries
                WHERE status = 'leased'
                """
            )
            row = cur.fetchone()
            return int(row[0] or 0) if row is not None else 0

    def write_frontier_snapshot(
        self,
        snapshot: dict[str, Any],
        *,
        generated_at: int | None = None,
        last_error: str | None = None,
    ) -> dict[str, Any]:
        timestamp = int(time.time())
        snapshot_generated_at = timestamp if generated_at is None else generated_at
        with db_transaction(self.db_path) as cur:
            self.ensure_frontier_snapshot_row(cur, now=timestamp)
            ph = sql_placeholder()
            cur.execute(
                f"""
                UPDATE frontier_snapshot
                SET
                    generated_at = {ph},
                    snapshot_json = {ph},
                    last_error = {ph},
                    updated_at = {ph}
                WHERE name = {ph}
                """,
                (
                    snapshot_generated_at,
                    Json(snapshot),
                    last_error,
                    timestamp,
                    _FRONTIER_ADMIN_ROW_NAME,
                ),
            )
        return {
            "generated_at": snapshot_generated_at,
            "snapshot": dict(snapshot),
            "last_error": last_error,
        }

    def record_frontier_snapshot_error(self, last_error: str) -> None:
        timestamp = int(time.time())
        with db_transaction(self.db_path) as cur:
            self.ensure_frontier_snapshot_row(cur, now=timestamp)
            ph = sql_placeholder()
            cur.execute(
                f"""
                UPDATE frontier_snapshot
                SET
                    last_error = {ph},
                    updated_at = {ph}
                WHERE name = {ph}
                """,
                (last_error, timestamp, _FRONTIER_ADMIN_ROW_NAME),
            )

    def get_frontier_snapshot_record(self) -> dict[str, Any]:
        with db_connection(self.db_path) as cur:
            ph = sql_placeholder()
            cur.execute(
                f"""
                SELECT generated_at, snapshot_json, last_error
                FROM frontier_snapshot
                WHERE name = {ph}
                """,
                (_FRONTIER_ADMIN_ROW_NAME,),
            )
            row = cur.fetchone()
            if row is None:
                return {
                    "generated_at": None,
                    "snapshot": {},
                    "last_error": None,
                }
            return {
                "generated_at": int(row[0]) if row[0] is not None else None,
                "snapshot": self._decode_snapshot_json(row[1]),
                "last_error": row[2],
            }

    def get_frontier_snapshot_payload(
        self,
        *,
        snapshot_ttl_sec: int,
        empty_snapshot: dict[str, Any],
        now: int | None = None,
    ) -> dict[str, Any]:
        record = self.get_frontier_snapshot_record()
        snapshot = dict(empty_snapshot)
        for key, value in record["snapshot"].items():
            if isinstance(snapshot.get(key), dict) and isinstance(value, dict):
                nested = dict(snapshot[key])
                nested.update(value)
                snapshot[key] = nested
                continue
            snapshot[key] = value
        current_time = int(time.time()) if now is None else now
        generated_at = record["generated_at"]
        if generated_at is None:
            snapshot["snapshot_age_seconds"] = 0
            snapshot["snapshot_stale"] = True
        else:
            age_seconds = max(0, current_time - generated_at)
            snapshot["snapshot_age_seconds"] = age_seconds
            snapshot["snapshot_stale"] = age_seconds >= snapshot_ttl_sec
        return snapshot

    def get_frontier_dashboard_summary(
        self,
        *,
        snapshot_ttl_sec: int,
        now: int | None = None,
    ) -> dict[str, int | bool]:
        current_time = int(time.time()) if now is None else now
        counters = self.get_frontier_counters()
        snapshot_record = self.get_frontier_snapshot_record()
        generated_at = snapshot_record["generated_at"]
        age_seconds = 0
        snapshot_stale = True
        if generated_at is not None:
            age_seconds = max(0, current_time - generated_at)
            snapshot_stale = age_seconds >= snapshot_ttl_sec
        snapshot_url_stats = snapshot_record["snapshot"].get("url_stats") or {}
        snapshot_frontier_status_counts = (
            snapshot_record["snapshot"].get("frontier_status_counts") or {}
        )
        total_seen = int(snapshot_url_stats.get("total") or 0)
        pending_rows = counters["pending_rows"]
        if not snapshot_stale:
            pending_rows = int(
                snapshot_frontier_status_counts.get("pending", pending_rows) or 0
            )
        leased_rows = self.get_live_leased_rows()
        return {
            "frontier_pending": pending_rows,
            "leased_tasks": leased_rows,
            "total_seen": total_seen,
            "frontier_snapshot_age_seconds": age_seconds,
            "frontier_snapshot_stale": snapshot_stale,
        }
