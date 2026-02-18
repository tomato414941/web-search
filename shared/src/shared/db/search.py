"""
PostgreSQL Database Module (Shared Kernel)

Schema definitions and database operations for the search index.
Used by both Frontend (Read) and Indexer (Write) services.
Requires DATABASE_URL environment variable (PostgreSQL only).
"""

import atexit
import logging
import os
import threading
from typing import Any
from shared.core.infrastructure_config import settings

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

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
  embedding vector(1536)
);
CREATE INDEX IF NOT EXISTS idx_page_embeddings_hnsw
  ON page_embeddings USING hnsw (embedding vector_cosine_ops);

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
CREATE INDEX IF NOT EXISTS idx_inverted_url ON inverted_index(url);

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

-- ============================================
-- Indexer Async Job Queue
-- ============================================

CREATE TABLE IF NOT EXISTS index_jobs (
  job_id TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  outlinks JSONB NOT NULL DEFAULT '[]'::jsonb,
  status TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  max_retries INTEGER NOT NULL DEFAULT 5,
  available_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
  lease_until BIGINT,
  worker_id TEXT,
  last_error TEXT,
  created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
  updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
  content_hash TEXT NOT NULL,
  dedupe_key TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_index_jobs_status_available ON index_jobs(status, available_at);
CREATE INDEX IF NOT EXISTS idx_index_jobs_status_lease ON index_jobs(status, lease_until);
CREATE INDEX IF NOT EXISTS idx_index_jobs_created ON index_jobs(created_at);
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


_pg_pool = None
_pg_pool_lock = threading.Lock()

DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "4"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "50"))


class _PooledConnection:
    """Wrapper that returns connection to pool on .close()."""

    def __init__(self, conn: Any, pool: Any):
        self._conn = conn
        self._pool = pool

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._pool.putconn(self._conn)
            except Exception:
                pass
            self._conn = None

    def cursor(self, *args: Any, **kwargs: Any) -> Any:
        return self._conn.cursor(*args, **kwargs)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def __enter__(self) -> "_PooledConnection":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


def _get_pg_pool() -> Any:
    """Get or create the PostgreSQL connection pool (singleton)."""
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool

    with _pg_pool_lock:
        if _pg_pool is not None:
            return _pg_pool

        import psycopg2.pool

        database_url = os.getenv("DATABASE_URL")
        _pg_pool = psycopg2.pool.ThreadedConnectionPool(
            DB_POOL_MIN, DB_POOL_MAX, database_url
        )
        logger.info(
            "PostgreSQL connection pool created (min=%d, max=%d)",
            DB_POOL_MIN,
            DB_POOL_MAX,
        )
        atexit.register(_close_pg_pool)
        return _pg_pool


def _close_pg_pool() -> None:
    global _pg_pool
    if _pg_pool is not None:
        try:
            _pg_pool.closeall()
        except Exception:
            pass
        _pg_pool = None


def get_connection(db_path: str | None = None) -> Any:
    """Get database connection.

    Production: PostgreSQL via connection pool (requires DATABASE_URL).
    Test: SQLite fallback when DATABASE_URL is not set.

    Args:
        db_path: Path to SQLite database (test only, ignored when DATABASE_URL is set).
    """
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        pool = _get_pg_pool()
        conn = pool.getconn()
        return _PooledConnection(conn, pool)

    # SQLite fallback for tests
    import sqlite3

    path = db_path or os.getenv("SEARCH_DB", settings.DB_PATH)
    return sqlite3.connect(path)


def _execute_pg_schema(con: Any, schema: str) -> None:
    """Execute PostgreSQL schema statements with advisory lock serialization."""
    cur = con.cursor()
    statements = [s.strip() for s in schema.split(";") if s.strip()]

    # Separate vector index statements (may fail on pre-migration BYTEA columns)
    core_stmts = []
    vector_idx_stmts = []
    for s in statements:
        if "hnsw" in s.lower() or "vector_cosine_ops" in s.lower():
            vector_idx_stmts.append(s)
        else:
            core_stmts.append(s)

    # Serialize schema initialization across multi-worker startup.
    lock_id = 906115423
    error: Exception | None = None
    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
    try:
        for stmt in core_stmts:
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

    # Try vector index creation separately (fails gracefully pre-migration)
    for stmt in vector_idx_stmts:
        try:
            cur2 = con.cursor()
            cur2.execute(stmt)
            con.commit()
            cur2.close()
        except Exception as e:
            con.rollback()
            logger.warning("Skipping vector index (run migration first): %s", e)


def _pg_schema_to_sqlite(schema: str) -> str:
    """Convert PostgreSQL schema to SQLite-compatible DDL for tests."""
    import re

    # Process as full text first: remove multi-line HNSW index statements
    text = re.sub(
        r"CREATE INDEX[^;]*USING\s+hnsw[^;]*;",
        "",
        schema,
        flags=re.IGNORECASE | re.DOTALL,
    )

    lines = []
    for line in text.splitlines():
        stripped = line.strip().upper()
        if stripped.startswith("CREATE EXTENSION"):
            continue
        # PG type casts: value::type
        line = re.sub(r"::\w+", "", line)
        # EXTRACT(EPOCH FROM NOW()) → strftime('%s', 'now')
        line = re.sub(
            r"EXTRACT\s*\(\s*EPOCH\s+FROM\s+NOW\(\)\s*\)",
            "(strftime('%s', 'now'))",
            line,
            flags=re.IGNORECASE,
        )
        line = re.sub(r"SERIAL\b", "INTEGER", line, flags=re.IGNORECASE)
        line = re.sub(
            r"TIMESTAMP\s+DEFAULT\s+NOW\(\)",
            "TEXT DEFAULT CURRENT_TIMESTAMP",
            line,
            flags=re.IGNORECASE,
        )
        line = re.sub(r"\bTIMESTAMP\b", "TEXT", line, flags=re.IGNORECASE)
        line = re.sub(r"\bJSONB\b", "TEXT", line, flags=re.IGNORECASE)
        line = re.sub(r"\bBIGINT\b", "INTEGER", line, flags=re.IGNORECASE)
        line = re.sub(r"\bvector\(\d+\)", "BLOB", line, flags=re.IGNORECASE)
        lines.append(line)
    return "\n".join(lines)


def open_db(path: str = settings.DB_PATH) -> Any:
    """Open database connection and ensure schema exists."""
    con = get_connection(path)
    if is_postgres_mode():
        _execute_pg_schema(con, SCHEMA_SQL)
    else:
        # SQLite (tests): convert PG schema to SQLite-compatible DDL
        con.executescript(_pg_schema_to_sqlite(SCHEMA_SQL))
    return con


def ensure_db(path: str = settings.DB_PATH) -> None:
    """Ensure database file exists with correct schema."""
    con = open_db(path)
    con.close()
