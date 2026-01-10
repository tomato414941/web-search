"""
Crawl History Database

SQLite-based crawl history tracking.
"""

import sqlite3
from typing import Optional, List, Dict, Any
from pathlib import Path

# Default DB path (can be overridden by environment variable)
DEFAULT_DB_PATH = "/data/crawler_history.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS crawl_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    status TEXT NOT NULL,  -- 'success', 'error', 'blocked', 'skipped'
    http_code INTEGER,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_history_url ON crawl_history(url);
CREATE INDEX IF NOT EXISTS idx_history_created ON crawl_history(created_at);
"""


def get_db_path() -> str:
    """Get database path from config or use default"""
    import os

    return os.getenv("CRAWLER_HISTORY_DB", DEFAULT_DB_PATH)


def init_db(db_path: str | None = None):
    """Initialize history database"""
    path = db_path or get_db_path()

    # Ensure directory exists
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as con:
        con.executescript(SCHEMA)


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
        with sqlite3.connect(path) as con:
            con.execute(
                "INSERT INTO crawl_history (url, status, http_code, error_message) VALUES (?, ?, ?, ?)",
                (url, status, http_code, error_message),
            )
    except Exception as e:
        print(f"Failed to log history: {e}")


def get_recent_history(
    limit: int = 50, db_path: str | None = None
) -> List[Dict[str, Any]]:
    """Get recent crawl logs"""
    try:
        path = db_path or get_db_path()
        with sqlite3.connect(path) as con:
            con.row_factory = sqlite3.Row
            cursor = con.execute(
                "SELECT * FROM crawl_history ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []


def get_url_history(
    url: str, limit: int = 10, db_path: str | None = None
) -> List[Dict[str, Any]]:
    """Get history for a specific URL"""
    try:
        path = db_path or get_db_path()
        with sqlite3.connect(path) as con:
            con.row_factory = sqlite3.Row
            cursor = con.execute(
                "SELECT * FROM crawl_history WHERE url = ? ORDER BY created_at DESC LIMIT ?",
                (url, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []
