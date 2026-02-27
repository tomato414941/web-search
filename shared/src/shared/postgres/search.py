"""
PostgreSQL Database Module (Shared Kernel)

Connection pool and utilities for the search index.
Used by both Frontend (Read) and Indexer (Write) services.
Requires DATABASE_URL environment variable (PostgreSQL only).

Schema is managed by Alembic (see db/alembic/).
"""

import atexit
import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

# Kept as a constant for backward compatibility (referenced by tests and re-exports).
# Schema creation is now handled by Alembic migrations.
SCHEMA_SQL = ""


def sql_placeholder() -> str:
    """Return PostgreSQL parameter placeholder."""
    return "%s"


def sql_placeholders(count: int) -> str:
    """Return comma-separated placeholders for IN clauses."""
    if count <= 0:
        raise ValueError("count must be greater than zero")
    return ",".join(["%s"] * count)


_pg_pool = None
_pg_pool_lock = threading.Lock()

DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "4"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))


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
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL environment variable is required. "
                "Set it to a PostgreSQL connection string."
            )
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
    """Get PostgreSQL database connection from the connection pool.

    Args:
        db_path: Deprecated, ignored. Kept for backward compatibility.
    """
    pool = _get_pg_pool()
    conn = pool.getconn()
    return _PooledConnection(conn, pool)


def open_db(path: str | None = None) -> Any:
    """Open database connection.

    Schema creation is now handled by Alembic.
    Args:
        path: Deprecated, ignored.
    """
    return get_connection(path)


def ensure_db(path: str | None = None) -> None:
    """Verify database connectivity (schema managed by Alembic).

    Args:
        path: Deprecated, ignored.
    """
    con = get_connection(path)
    con.close()
