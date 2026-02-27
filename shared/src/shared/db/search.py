"""Backward-compatible re-exports. Use shared.postgres.search instead."""

from shared.postgres.search import (  # noqa: F401
    SCHEMA_SQL,
    ensure_db,
    get_connection,
    open_db,
    sql_placeholder,
    sql_placeholders,
)
