"""
Crawl Logs Database

PostgreSQL/SQLite-based crawl attempt logging.
"""

from typing import Optional, List, Dict, Any
from pathlib import Path

from shared.db.search import get_connection, is_postgres_mode

# Default DB path (can be overridden by environment variable)
# Unified crawler database for all crawler-related tables
DEFAULT_DB_PATH = "/data/crawler.db"


def _placeholder() -> str:
    """Return the appropriate placeholder for the current database."""
    return "%s" if is_postgres_mode() else "?"


# Note: seen_urls table is defined in shared/db/seen_store.py
SCHEMA_PG = """
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

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS crawl_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    status TEXT NOT NULL,
    http_code INTEGER,
    error_message TEXT,
    created_at INTEGER DEFAULT (strftime('%s', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_crawl_logs_url ON crawl_logs(url);
CREATE INDEX IF NOT EXISTS idx_crawl_logs_created ON crawl_logs(created_at);
"""


def get_db_path() -> str:
    """Get database path from config or use default"""
    import os

    return os.getenv("CRAWLER_HISTORY_DB", DEFAULT_DB_PATH)


def init_db(db_path: str | None = None):
    """Initialize crawler database (PostgreSQL or local SQLite with WAL mode)"""
    path = db_path or get_db_path()
    postgres_mode = is_postgres_mode()

    # Ensure directory exists (only for local SQLite)
    if not postgres_mode:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    con = get_connection(path)
    try:
        if postgres_mode:
            cur = con.cursor()
            for stmt in SCHEMA_PG.split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)
            con.commit()
            cur.close()
        else:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(SCHEMA_SQLITE)
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
        ph = _placeholder()
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
        print(f"Failed to log history: {e}")


def get_recent_history(
    limit: int = 50, db_path: str | None = None
) -> List[Dict[str, Any]]:
    """Get recent crawl logs"""
    try:
        path = db_path or get_db_path()
        ph = _placeholder()
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
    except Exception:
        return []


def get_crawl_rate(hours: int = 1, db_path: str | None = None) -> int:
    """Get count of crawl attempts in the last N hours (computed via SQL)."""
    try:
        path = db_path or get_db_path()
        ph = _placeholder()
        con = get_connection(path)
        try:
            import time

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
    except Exception:
        return 0


def get_error_count(hours: int = 1, db_path: str | None = None) -> int:
    """Get count of error crawl attempts in the last N hours."""
    try:
        path = db_path or get_db_path()
        ph = _placeholder()
        con = get_connection(path)
        try:
            import time

            cutoff = int(time.time()) - (hours * 3600)
            cur = con.cursor()
            cur.execute(
                f"SELECT COUNT(*) FROM crawl_logs WHERE status = 'error' AND created_at >= {ph}",
                (cutoff,),
            )
            result = cur.fetchone()[0]
            cur.close()
            return result
        finally:
            con.close()
    except Exception:
        return 0


def get_recent_errors(
    limit: int = 5, db_path: str | None = None
) -> List[Dict[str, Any]]:
    """Get most recent error entries."""
    try:
        path = db_path or get_db_path()
        ph = _placeholder()
        con = get_connection(path)
        try:
            cur = con.cursor()
            cur.execute(
                f"SELECT url, error_message, created_at FROM crawl_logs "
                f"WHERE status = 'error' ORDER BY created_at DESC LIMIT {ph}",
                (limit,),
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
    except Exception:
        return []


def get_url_history(
    url: str, limit: int = 10, db_path: str | None = None
) -> List[Dict[str, Any]]:
    """Get history for a specific URL"""
    try:
        path = db_path or get_db_path()
        ph = _placeholder()
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
    except Exception:
        return []
