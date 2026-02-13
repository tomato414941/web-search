from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from shared.db.search import get_connection


@contextmanager
def db_cursor(db_path: str) -> Iterator[tuple[Any, Any]]:
    """Yield a DB connection and cursor, always closing both."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        yield conn, cursor
    finally:
        try:
            cursor.close()
        finally:
            conn.close()
