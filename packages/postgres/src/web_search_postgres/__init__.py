"""PostgreSQL database access layer."""

from web_search_postgres.search import (
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
