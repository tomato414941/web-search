"""Backward-compatible re-exports. Use shared.postgres.search instead."""

from shared.postgres.search import (  # noqa: F401
    SCHEMA_SQL,
    _pg_schema_to_sqlite,
    ensure_db,
    get_connection,
    is_postgres_mode,
    open_db,
    sql_placeholder,
    sql_placeholders,
)
