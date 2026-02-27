"""PostgreSQL database access layer."""

from shared.postgres.search import (
    ensure_db,
    get_connection,
    is_postgres_mode,
    open_db,
    sql_placeholder,
    sql_placeholders,
)

__all__ = [
    "ensure_db",
    "get_connection",
    "is_postgres_mode",
    "open_db",
    "sql_placeholder",
    "sql_placeholders",
]
