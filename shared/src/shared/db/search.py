"""
SQLite Database Module (Shared Kernel)

Schema definitions and database operations for the search index.
Used by both Frontend (Read) and Indexer (Write) services.

Supports both:
- Turso (production): Set TURSO_URL and TURSO_TOKEN environment variables
- Local SQLite (development): Uses SEARCH_DB path or default
"""

import os
import sqlite3
from shared.core.infrastructure_config import settings

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS links (
  src TEXT,
  dst TEXT
);
CREATE INDEX IF NOT EXISTS idx_links_src ON links(src);
CREATE INDEX IF NOT EXISTS idx_links_dst ON links(dst);

CREATE TABLE IF NOT EXISTS page_ranks (
  url TEXT PRIMARY KEY,
  score REAL
);

CREATE TABLE IF NOT EXISTS page_embeddings (
  url TEXT PRIMARY KEY,
  embedding BLOB
);

-- ============================================
-- Custom Full-Text Search Tables
-- ============================================

-- Document metadata
CREATE TABLE IF NOT EXISTS documents (
  url TEXT PRIMARY KEY,
  title TEXT,
  content TEXT,
  word_count INTEGER DEFAULT 0,
  indexed_at TEXT
);

-- Inverted index (heart of the search engine)
CREATE TABLE IF NOT EXISTS inverted_index (
  token TEXT NOT NULL,
  url TEXT NOT NULL,
  field TEXT NOT NULL,        -- 'title' or 'content'
  term_freq INTEGER DEFAULT 1,
  positions TEXT,             -- JSON array of positions
  PRIMARY KEY (token, url, field)
);
CREATE INDEX IF NOT EXISTS idx_inverted_token ON inverted_index(token);

-- Global index statistics (for BM25)
CREATE TABLE IF NOT EXISTS index_stats (
  key TEXT PRIMARY KEY,
  value REAL
);

-- Per-token document frequency (for IDF calculation)
CREATE TABLE IF NOT EXISTS token_stats (
  token TEXT PRIMARY KEY,
  doc_freq INTEGER DEFAULT 0
);

-- ============================================
-- Search Analytics Tables
-- ============================================

CREATE TABLE IF NOT EXISTS search_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  query TEXT NOT NULL,
  result_count INTEGER DEFAULT 0,
  search_mode TEXT DEFAULT 'default',
  user_agent TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_search_logs_created ON search_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_search_logs_query ON search_logs(query);
"""


def get_connection(db_path: str | None = None):
    """Get database connection (Turso or local SQLite).

    Args:
        db_path: Optional path to SQLite database. Ignored if TURSO_URL is set.

    Returns a connection object that is compatible with sqlite3.Connection.
    - If TURSO_URL is set: connects to Turso (production)
    - Otherwise: connects to local SQLite (development)
    """
    turso_url = os.getenv("TURSO_URL")

    if turso_url:
        # Turso (production)
        import libsql_experimental as libsql

        return libsql.connect(turso_url, auth_token=os.getenv("TURSO_TOKEN"))
    else:
        # Local SQLite (development)
        path = db_path or os.getenv("SEARCH_DB", settings.DB_PATH)
        return sqlite3.connect(path)


def open_db(path: str = settings.DB_PATH):
    """Open database connection and ensure schema exists.

    Note: If TURSO_URL is set, the path parameter is ignored
    and Turso connection is used instead.
    """
    con = get_connection(path)
    turso_mode = os.getenv("TURSO_URL") is not None
    if turso_mode:
        # Skip PRAGMA statements (Turso manages these automatically)
        schema_without_pragmas = "\n".join(
            line
            for line in SCHEMA_SQL.split("\n")
            if not line.strip().startswith("PRAGMA")
        )
        con.executescript(schema_without_pragmas)
    else:
        con.executescript(SCHEMA_SQL)
    return con


def ensure_db(path: str = settings.DB_PATH) -> None:
    """Ensure database file exists with correct schema."""
    con = open_db(path)
    con.close()
