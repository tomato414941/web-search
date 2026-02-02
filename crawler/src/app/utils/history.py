"""
Crawl History Database

SQLite/Turso-based crawl history tracking.
"""

import os
from typing import Optional, List, Dict, Any
from pathlib import Path

from shared.db.search import get_connection

# Default DB path (can be overridden by environment variable)
# Unified crawler database for all crawler-related tables
DEFAULT_DB_PATH = "/data/crawler.db"

# Note: seen_urls table is defined in shared/db/seen_store.py
SCHEMA = """
-- Crawl history (audit/analysis)
CREATE TABLE IF NOT EXISTS crawl_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    status TEXT NOT NULL,  -- 'success', 'error', 'blocked', 'skipped'
    http_code INTEGER,
    error_message TEXT,
    created_at INTEGER DEFAULT (strftime('%s', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_history_url ON crawl_history(url);
CREATE INDEX IF NOT EXISTS idx_history_created ON crawl_history(created_at);
"""


def get_db_path() -> str:
    """Get database path from config or use default"""
    import os

    return os.getenv("CRAWLER_HISTORY_DB", DEFAULT_DB_PATH)


def init_db(db_path: str | None = None):
    """Initialize crawler database (Turso or local SQLite with WAL mode)"""
    path = db_path or get_db_path()
    turso_mode = os.getenv("TURSO_URL") is not None

    # Ensure directory exists (only for local SQLite)
    if not turso_mode:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    con = get_connection(path)
    try:
        if not turso_mode:
            con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
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
        con = get_connection(path)
        try:
            con.execute(
                "INSERT INTO crawl_history (url, status, http_code, error_message) VALUES (?, ?, ?, ?)",
                (url, status, http_code, error_message),
            )
            con.commit()
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
        con = get_connection(path)
        try:
            cursor = con.execute(
                "SELECT id, url, status, http_code, error_message, created_at "
                "FROM crawl_history ORDER BY created_at DESC LIMIT ?",
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
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
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
        con = get_connection(path)
        try:
            cursor = con.execute(
                "SELECT id, url, status, http_code, error_message, created_at "
                "FROM crawl_history WHERE url = ? ORDER BY created_at DESC LIMIT ?",
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
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            con.close()
    except Exception:
        return []
