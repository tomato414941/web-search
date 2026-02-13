"""
PostgreSQL Database Module (Shared Kernel)

Schema definitions and database operations for the search index.
Used by both Frontend (Read) and Indexer (Write) services.

Supports both:
- PostgreSQL (production): Set DATABASE_URL environment variable
- Local SQLite (development): Uses SEARCH_DB path or default
"""

import os
from typing import Any
from shared.core.infrastructure_config import settings, Environment

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS links (
  src TEXT NOT NULL,
  dst TEXT NOT NULL,
  PRIMARY KEY (src, dst)
);
CREATE INDEX IF NOT EXISTS idx_links_src ON links(src);
CREATE INDEX IF NOT EXISTS idx_links_dst ON links(dst);

CREATE TABLE IF NOT EXISTS page_ranks (
  url TEXT PRIMARY KEY,
  score REAL
);

CREATE TABLE IF NOT EXISTS domain_ranks (
  domain TEXT PRIMARY KEY,
  score REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS page_embeddings (
  url TEXT PRIMARY KEY,
  embedding BYTEA
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
  indexed_at TIMESTAMP
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
  id SERIAL PRIMARY KEY,
  query TEXT NOT NULL,
  result_count INTEGER DEFAULT 0,
  search_mode TEXT DEFAULT 'default',
  user_agent TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_search_logs_created ON search_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_search_logs_query ON search_logs(query);

CREATE TABLE IF NOT EXISTS search_events (
  id SERIAL PRIMARY KEY,
  event_type TEXT NOT NULL,
  query TEXT NOT NULL,
  query_norm TEXT NOT NULL,
  request_id TEXT,
  session_hash TEXT,
  result_count INTEGER,
  clicked_url TEXT,
  clicked_rank INTEGER,
  latency_ms INTEGER,
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_search_events_created ON search_events(created_at);
CREATE INDEX IF NOT EXISTS idx_search_events_type_created ON search_events(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_search_events_query_created ON search_events(query_norm, created_at);
CREATE INDEX IF NOT EXISTS idx_search_events_request_id ON search_events(request_id);
"""

# SQLite schema for local development
SQLITE_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS links (
  src TEXT NOT NULL,
  dst TEXT NOT NULL,
  PRIMARY KEY (src, dst)
);
CREATE INDEX IF NOT EXISTS idx_links_src ON links(src);
CREATE INDEX IF NOT EXISTS idx_links_dst ON links(dst);

CREATE TABLE IF NOT EXISTS page_ranks (
  url TEXT PRIMARY KEY,
  score REAL
);

CREATE TABLE IF NOT EXISTS domain_ranks (
  domain TEXT PRIMARY KEY,
  score REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS page_embeddings (
  url TEXT PRIMARY KEY,
  embedding BLOB
);

-- Document metadata
CREATE TABLE IF NOT EXISTS documents (
  url TEXT PRIMARY KEY,
  title TEXT,
  content TEXT,
  word_count INTEGER DEFAULT 0,
  indexed_at TEXT
);

-- Inverted index
CREATE TABLE IF NOT EXISTS inverted_index (
  token TEXT NOT NULL,
  url TEXT NOT NULL,
  field TEXT NOT NULL,
  term_freq INTEGER DEFAULT 1,
  positions TEXT,
  PRIMARY KEY (token, url, field)
);
CREATE INDEX IF NOT EXISTS idx_inverted_token ON inverted_index(token);

-- Global index statistics
CREATE TABLE IF NOT EXISTS index_stats (
  key TEXT PRIMARY KEY,
  value REAL
);

-- Per-token document frequency
CREATE TABLE IF NOT EXISTS token_stats (
  token TEXT PRIMARY KEY,
  doc_freq INTEGER DEFAULT 0
);

-- Search Analytics
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

CREATE TABLE IF NOT EXISTS search_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  query TEXT NOT NULL,
  query_norm TEXT NOT NULL,
  request_id TEXT,
  session_hash TEXT,
  result_count INTEGER,
  clicked_url TEXT,
  clicked_rank INTEGER,
  latency_ms INTEGER,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_search_events_created ON search_events(created_at);
CREATE INDEX IF NOT EXISTS idx_search_events_type_created ON search_events(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_search_events_query_created ON search_events(query_norm, created_at);
CREATE INDEX IF NOT EXISTS idx_search_events_request_id ON search_events(request_id);
"""


def is_postgres_mode() -> bool:
    """Check if we're using PostgreSQL."""
    return os.getenv("DATABASE_URL") is not None


def sql_placeholder() -> str:
    """Return parameter placeholder for current database driver."""
    return "%s" if is_postgres_mode() else "?"


def sql_placeholders(count: int) -> str:
    """Return comma-separated placeholders for IN clauses."""
    if count <= 0:
        raise ValueError("count must be greater than zero")
    ph = sql_placeholder()
    return ",".join([ph] * count)


def get_connection(db_path: str | None = None) -> Any:
    """Get database connection (PostgreSQL or local SQLite).

    Args:
        db_path: Optional path to SQLite database. Ignored if DATABASE_URL is set.

    Returns a connection object.
    - If DATABASE_URL is set: connects to PostgreSQL (production)
    - Otherwise: connects to local SQLite (development/test only)

    Raises:
        RuntimeError: If ENVIRONMENT is 'production' but DATABASE_URL is not set.
    """
    database_url = os.getenv("DATABASE_URL")

    if settings.ENVIRONMENT == Environment.PRODUCTION and not database_url:
        raise RuntimeError(
            "DATABASE_URL is required in production environment. "
            "Set DATABASE_URL environment variable."
        )

    if database_url:
        # PostgreSQL (production)
        import psycopg2

        return psycopg2.connect(database_url)
    else:
        # Local SQLite (development)
        import sqlite3

        path = db_path or os.getenv("SEARCH_DB", settings.DB_PATH)
        return sqlite3.connect(path)


def _execute_schema_statements(con: Any, schema: str, is_postgres: bool) -> None:
    """Execute schema statements one by one for PostgreSQL compatibility."""
    if is_postgres:
        cur = con.cursor()
        statements = [s.strip() for s in schema.split(";") if s.strip()]
        # Serialize schema initialization across multi-worker startup.
        # Without this lock, concurrent CREATE TABLE IF NOT EXISTS can still race
        # on PostgreSQL catalogs and raise duplicate key errors.
        lock_id = 906115423
        error: Exception | None = None
        cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
        try:
            for stmt in statements:
                cur.execute(stmt)
            con.commit()
        except Exception as e:
            error = e
            con.rollback()
        finally:
            try:
                cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
                con.commit()
            except Exception:
                con.rollback()
                if error is None:
                    raise
            finally:
                cur.close()

        if error is not None:
            raise error
    else:
        con.executescript(schema)


def open_db(path: str = settings.DB_PATH) -> Any:
    """Open database connection and ensure schema exists.

    Note: If DATABASE_URL is set, the path parameter is ignored
    and PostgreSQL connection is used instead.
    """
    con = get_connection(path)
    postgres_mode = is_postgres_mode()

    if postgres_mode:
        _execute_schema_statements(con, SCHEMA_SQL, is_postgres=True)
    else:
        con.executescript(SQLITE_SCHEMA_SQL)

    return con


def ensure_db(path: str = settings.DB_PATH) -> None:
    """Ensure database file exists with correct schema."""
    con = open_db(path)
    con.close()
