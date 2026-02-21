"""
Crawl Logs Database

PostgreSQL/SQLite-based crawl attempt logging.
"""

import logging
import time
from typing import Optional, List, Dict, Any, Set
from pathlib import Path
from urllib.parse import urlparse

from shared.db.search import (
    get_connection,
    is_postgres_mode,
    sql_placeholder,
    sql_placeholders,
    _pg_schema_to_sqlite,
)

logger = logging.getLogger(__name__)

# Default DB path (can be overridden by environment variable)
# Unified crawler database for all crawler-related tables
DEFAULT_DB_PATH = "/data/crawler.db"


# Note: seen_urls table is defined in shared/db/seen_store.py
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS crawl_logs (
    id SERIAL PRIMARY KEY,
    url TEXT NOT NULL,
    status TEXT NOT NULL,
    http_code INTEGER,
    error_message TEXT,
    created_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW())::INTEGER
);
CREATE INDEX IF NOT EXISTS idx_crawl_logs_url ON crawl_logs(url);
CREATE INDEX IF NOT EXISTS idx_crawl_logs_created ON crawl_logs(created_at);
"""

ERROR_STATUSES = ("indexer_error", "http_error", "unknown_error", "dead_letter")


def get_db_path() -> str:
    """Get database path from config or use default"""
    import os

    return os.getenv("CRAWLER_HISTORY_DB", DEFAULT_DB_PATH)


def init_db(db_path: str | None = None):
    """Initialize crawler database."""
    path = db_path or get_db_path()
    pg = is_postgres_mode()

    if not pg:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    con = get_connection(path)
    try:
        if pg:
            cur = con.cursor()
            for stmt in SCHEMA_SQL.split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)
            con.commit()
            cur.close()
        else:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(_pg_schema_to_sqlite(SCHEMA_SQL))
    finally:
        con.close()


def log_crawl_attempt(
    url: str,
    status: str,
    http_code: Optional[int] = None,
    error_message: Optional[str] = None,
    db_path: str | None = None,
):
    """Log a crawl attempt to history"""
    try:
        path = db_path or get_db_path()
        ph = sql_placeholder()
        con = get_connection(path)
        try:
            cur = con.cursor()
            cur.execute(
                f"INSERT INTO crawl_logs (url, status, http_code, error_message) VALUES ({ph}, {ph}, {ph}, {ph})",
                (url, status, http_code, error_message),
            )
            con.commit()
            cur.close()
        finally:
            con.close()
    except Exception as e:
        logger.warning(f"Failed to log crawl history for {url}: {e}")


def get_recent_history(
    limit: int = 50, db_path: str | None = None
) -> List[Dict[str, Any]]:
    """Get recent crawl logs"""
    try:
        path = db_path or get_db_path()
        ph = sql_placeholder()
        con = get_connection(path)
        try:
            cur = con.cursor()
            cur.execute(
                f"SELECT id, url, status, http_code, error_message, created_at "
                f"FROM crawl_logs ORDER BY created_at DESC LIMIT {ph}",
                (limit,),
            )
            columns = [
                "id",
                "url",
                "status",
                "http_code",
                "error_message",
                "created_at",
            ]
            result = [dict(zip(columns, row)) for row in cur.fetchall()]
            cur.close()
            return result
        finally:
            con.close()
    except Exception as exc:
        logger.warning(f"Failed to fetch recent crawl history: {exc}")
        return []


def get_crawl_rate(hours: int = 1, db_path: str | None = None) -> int:
    """Get count of crawl attempts in the last N hours (computed via SQL)."""
    try:
        path = db_path or get_db_path()
        ph = sql_placeholder()
        con = get_connection(path)
        try:
            cutoff = int(time.time()) - (hours * 3600)
            cur = con.cursor()
            cur.execute(
                f"SELECT COUNT(*) FROM crawl_logs WHERE created_at >= {ph}",
                (cutoff,),
            )
            result = cur.fetchone()[0]
            cur.close()
            return result
        finally:
            con.close()
    except Exception as exc:
        logger.warning(f"Failed to fetch crawl rate for {hours}h window: {exc}")
        return 0


def get_error_count(hours: int = 1, db_path: str | None = None) -> int:
    """Get count of error crawl attempts in the last N hours."""
    try:
        path = db_path or get_db_path()
        ph = sql_placeholder()
        status_ph = sql_placeholders(len(ERROR_STATUSES))
        con = get_connection(path)
        try:
            cutoff = int(time.time()) - (hours * 3600)
            cur = con.cursor()
            cur.execute(
                f"""
                SELECT COUNT(*) FROM crawl_logs
                WHERE status IN ({status_ph}) AND created_at >= {ph}
                """,
                (*ERROR_STATUSES, cutoff),
            )
            result = cur.fetchone()[0]
            cur.close()
            return result
        finally:
            con.close()
    except Exception as exc:
        logger.warning(f"Failed to fetch crawl error count for {hours}h window: {exc}")
        return 0


def get_status_counts(
    hours: int | None = 1, db_path: str | None = None
) -> Dict[str, int]:
    """Get crawl attempt counts grouped by status.

    Args:
        hours: Time window in hours. None means all-time.
        db_path: Optional database path override.
    """
    try:
        path = db_path or get_db_path()
        ph = sql_placeholder()
        con = get_connection(path)
        try:
            cur = con.cursor()
            if hours is None:
                cur.execute("SELECT status, COUNT(*) FROM crawl_logs GROUP BY status")
            else:
                cutoff = int(time.time()) - (hours * 3600)
                cur.execute(
                    f"""
                    SELECT status, COUNT(*)
                    FROM crawl_logs
                    WHERE created_at >= {ph}
                    GROUP BY status
                    """,
                    (cutoff,),
                )
            status_counts = {
                str(status): int(count) for status, count in cur.fetchall()
            }
            cur.close()
            return status_counts
        finally:
            con.close()
    except Exception as exc:
        logger.warning(
            f"Failed to fetch crawl status counts for {hours}h window: {exc}"
        )
        return {}


def get_recent_errors(
    limit: int = 5, db_path: str | None = None
) -> List[Dict[str, Any]]:
    """Get most recent error entries."""
    try:
        path = db_path or get_db_path()
        ph = sql_placeholder()
        status_ph = sql_placeholders(len(ERROR_STATUSES))
        con = get_connection(path)
        try:
            cur = con.cursor()
            cur.execute(
                f"""
                SELECT url, error_message, created_at FROM crawl_logs
                WHERE status IN ({status_ph})
                ORDER BY created_at DESC LIMIT {ph}
                """,
                (*ERROR_STATUSES, limit),
            )
            result = [
                {
                    "url": row[0],
                    "error_message": row[1] or "Unknown",
                    "created_at": row[2],
                }
                for row in cur.fetchall()
            ]
            cur.close()
            return result
        finally:
            con.close()
    except Exception as exc:
        logger.warning(f"Failed to fetch recent crawl errors: {exc}")
        return []


def get_url_history(
    url: str, limit: int = 10, db_path: str | None = None
) -> List[Dict[str, Any]]:
    """Get history for a specific URL"""
    try:
        path = db_path or get_db_path()
        ph = sql_placeholder()
        con = get_connection(path)
        try:
            cur = con.cursor()
            cur.execute(
                f"SELECT id, url, status, http_code, error_message, created_at "
                f"FROM crawl_logs WHERE url = {ph} ORDER BY created_at DESC LIMIT {ph}",
                (url, limit),
            )
            columns = [
                "id",
                "url",
                "status",
                "http_code",
                "error_message",
                "created_at",
            ]
            result = [dict(zip(columns, row)) for row in cur.fetchall()]
            cur.close()
            return result
        finally:
            con.close()
    except Exception as exc:
        logger.warning(f"Failed to fetch crawl history for {url}: {exc}")
        return []


def get_robots_blocked_domains(
    hours: int = 24,
    min_count: int = 3,
    db_path: str | None = None,
) -> Set[str]:
    """Return domains with >= min_count robots.txt blocks in the last N hours."""
    try:
        path = db_path or get_db_path()
        ph = sql_placeholder()
        cutoff = int(time.time()) - hours * 3600
        con = get_connection(path)
        try:
            cur = con.cursor()
            cur.execute(
                f"SELECT url FROM crawl_logs "
                f"WHERE status = 'blocked' "
                f"AND error_message = 'Blocked by robots.txt' "
                f"AND created_at >= {ph}",
                (cutoff,),
            )
            domain_counts: dict[str, int] = {}
            for (url_val,) in cur.fetchall():
                d = urlparse(url_val).hostname
                if d:
                    domain_counts[d] = domain_counts.get(d, 0) + 1
            cur.close()
            return {d for d, c in domain_counts.items() if c >= min_count}
        finally:
            con.close()
    except Exception as exc:
        logger.warning(f"Failed to fetch robots blocked domains: {exc}")
        return set()


def get_robots_blocked_domains_with_counts(
    hours: int = 24,
    min_count: int = 3,
    db_path: str | None = None,
) -> List[Dict[str, Any]]:
    """Return domains with >= min_count robots.txt blocks and their counts."""
    try:
        path = db_path or get_db_path()
        ph = sql_placeholder()
        cutoff = int(time.time()) - hours * 3600
        con = get_connection(path)
        try:
            cur = con.cursor()
            cur.execute(
                f"SELECT url FROM crawl_logs "
                f"WHERE status = 'blocked' "
                f"AND error_message = 'Blocked by robots.txt' "
                f"AND created_at >= {ph}",
                (cutoff,),
            )
            domain_counts: dict[str, int] = {}
            for (url_val,) in cur.fetchall():
                d = urlparse(url_val).hostname
                if d:
                    domain_counts[d] = domain_counts.get(d, 0) + 1
            cur.close()
            return sorted(
                [
                    {"domain": d, "count": c}
                    for d, c in domain_counts.items()
                    if c >= min_count
                ],
                key=lambda x: x["count"],
                reverse=True,
            )
        finally:
            con.close()
    except Exception as exc:
        logger.warning(f"Failed to fetch robots blocked domains with counts: {exc}")
        return []


def get_high_failure_domains(
    hours: int = 24,
    min_count: int = 5,
    db_path: str | None = None,
) -> List[Dict[str, Any]]:
    """Return domains with high crawl failure rates in the given time window."""
    error_statuses = {
        "http_error",
        "indexer_error",
        "unknown_error",
        "dead_letter",
        "blocked",
    }
    try:
        path = db_path or get_db_path()
        ph = sql_placeholder()
        cutoff = int(time.time()) - hours * 3600
        con = get_connection(path)
        try:
            cur = con.cursor()
            cur.execute(
                f"SELECT url, status FROM crawl_logs WHERE created_at >= {ph}",
                (cutoff,),
            )
            domain_errors: dict[str, int] = {}
            domain_totals: dict[str, int] = {}
            for url_val, status in cur.fetchall():
                d = urlparse(url_val).hostname
                if not d:
                    continue
                domain_totals[d] = domain_totals.get(d, 0) + 1
                if status in error_statuses:
                    domain_errors[d] = domain_errors.get(d, 0) + 1
            cur.close()
            result = []
            for d, err_count in domain_errors.items():
                total = domain_totals.get(d, 0)
                if err_count >= min_count and total > 0:
                    result.append(
                        {
                            "domain": d,
                            "error_count": err_count,
                            "total_count": total,
                            "error_rate": round((err_count / total) * 100, 1),
                        }
                    )
            return sorted(result, key=lambda x: x["error_count"], reverse=True)[:20]
        finally:
            con.close()
    except Exception as exc:
        logger.warning(f"Failed to fetch high failure domains: {exc}")
        return []
