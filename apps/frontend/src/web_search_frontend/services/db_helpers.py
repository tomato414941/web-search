from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from web_search_postgres.search import get_connection


@contextmanager
def db_cursor() -> Iterator[tuple[Any, Any]]:
    """Yield a DB connection and cursor, always closing both."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        yield conn, cursor
    finally:
        try:
            cursor.close()
        finally:
            conn.close()
