"""
Database connection context managers.

Reduces boilerplate for the get_connection / try / finally / close pattern.
"""

from contextlib import contextmanager
from typing import Any, Generator

from shared.postgres.search import get_connection


@contextmanager
def db_connection(db_path: str | None = None) -> Generator[Any, None, None]:
    """Context manager for read-only DB operations.

    Yields a cursor; closes cursor and connection on exit.
    """
    con = get_connection(db_path)
    try:
        cur = con.cursor()
        try:
            yield cur
        finally:
            cur.close()
    finally:
        con.close()


@contextmanager
def db_transaction(db_path: str | None = None) -> Generator[Any, None, None]:
    """Context manager for DB write operations with auto-commit.

    Yields a cursor; commits on success, rolls back on exception.
    Closes cursor and connection on exit.
    """
    con = get_connection(db_path)
    try:
        cur = con.cursor()
        try:
            yield cur
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            cur.close()
    finally:
        con.close()
