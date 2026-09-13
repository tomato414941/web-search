"""Coordinate readers, uploads, compaction, and collection on the archive database."""

from contextlib import contextmanager
import os
from typing import Iterator

import psycopg2


@contextmanager
def archive_lock(
    *,
    exclusive: bool = False,
    maintenance: bool = False,
    uploader: bool = False,
    exporter: bool = False,
) -> Iterator[None]:
    # Dedicated connections prevent session locks leaking into the shared pool.
    con = psycopg2.connect(os.environ["DATABASE_URL"])
    con.autocommit = True
    try:
        with con.cursor() as cur:
            if maintenance:
                cur.execute("SELECT pg_advisory_lock(712043, 2)")
            if uploader:
                cur.execute("SELECT pg_advisory_lock(712043, 4)")
            if exporter:
                cur.execute("SELECT pg_advisory_lock(712043, 5)")
            name = "pg_advisory_lock" if exclusive else "pg_advisory_lock_shared"
            cur.execute(f"SELECT {name}(712043, 3)")
        yield
    finally:
        con.close()
