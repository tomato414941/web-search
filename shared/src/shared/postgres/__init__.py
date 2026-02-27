"""PostgreSQL database access layer."""

from shared.postgres.search import (
    ensure_db,
    get_connection,
    open_db,
    sql_placeholder,
    sql_placeholders,
)

__all__ = [
    "ensure_db",
    "get_connection",
    "open_db",
    "sql_placeholder",
    "sql_placeholders",
]
