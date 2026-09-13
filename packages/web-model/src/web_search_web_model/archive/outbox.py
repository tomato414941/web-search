"""Transactional, byte-bounded pending observations with stable upload batches."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import os
from typing import Any, Iterator
from uuid import uuid4

from web_search_postgres.search import get_connection
from web_search_web_model.archive.records import (
    BATCH_BYTES,
    BATCH_PAGES,
    FLUSH_SECONDS,
    Observation,
    utc_text,
)


class ArchiveFull(RuntimeError):
    """The crawler must wait for archive uploads before taking more work."""


def pending_limit() -> int:
    value = int(os.getenv("LINK_ARCHIVE_MAX_PENDING_BYTES", str(512 * 1024 * 1024)))
    if value < BATCH_BYTES:
        raise ValueError("LINK_ARCHIVE_MAX_PENDING_BYTES must be at least 16 MiB")
    return value


@contextmanager
def transaction() -> Iterator[Any]:
    con = get_connection()
    try:
        with con.cursor() as cur:
            yield cur
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def append_observation(cur: Any, src: str, host: str, outlinks: list[str]) -> None:
    cur.execute("SELECT nextval('link_observation_revision'), clock_timestamp()")
    revision, observed_at = cur.fetchone()
    payload = Observation(src, host, revision, utc_text(observed_at), outlinks).encode()
    cur.execute(
        """UPDATE link_archive_state SET pending_bytes = pending_bytes + %s
           WHERE singleton AND pending_bytes + %s <= %s RETURNING singleton""",
        (len(payload), len(payload), pending_limit()),
    )
    if cur.fetchone() is None:
        raise ArchiveFull("Link archive outbox is full; waiting for uploads")
    cur.execute(
        """INSERT INTO link_outbox (revision, payload, payload_bytes)
           VALUES (%s, %s, %s)""",
        (revision, payload.decode("utf-8"), len(payload)),
    )


def has_capacity() -> bool:
    with transaction() as cur:
        cur.execute("SELECT pending_bytes FROM link_archive_state WHERE singleton")
        return cur.fetchone()[0] <= pending_limit() - BATCH_BYTES


def status() -> dict[str, Any]:
    with transaction() as cur:
        cur.execute("""SELECT count(*), coalesce(sum(payload_bytes), 0),
            coalesce(extract(epoch FROM clock_timestamp() - min(created_at)), 0)
            FROM link_outbox""")
        count, size, age = cur.fetchone()
        cur.execute("""SELECT legacy_complete, legacy_pages, legacy_edges
            FROM link_archive_state WHERE singleton""")
        complete, pages, edges = cur.fetchone()
    return {
        "pending_pages": count,
        "pending_bytes": size,
        "oldest_pending_seconds": float(age),
        "legacy_export_complete": complete,
        "legacy_pages": pages,
        "legacy_edges": edges,
    }


@dataclass(frozen=True)
class Batch:
    batch_id: str
    created_at: datetime
    records: list[Observation]


def claim_batch(*, force: bool = False) -> Batch | None:
    """Resume an existing batch, or assign exact rows to a new stable batch ID."""
    with transaction() as cur:
        # Serializes assignment only; no network calls while holding this lock.
        cur.execute("SELECT pg_advisory_xact_lock(712043, 1)")
        cur.execute("""SELECT batch_id, created_at FROM link_archive_batches
            ORDER BY created_at, batch_id LIMIT 1""")
        existing = cur.fetchone()
        if existing:
            batch_id, created_at = existing
            cur.execute(
                """SELECT payload FROM link_outbox
                WHERE batch_id = %s ORDER BY revision""",
                (batch_id,),
            )
            return Batch(
                str(batch_id), created_at, [Observation.decode(row[0]) for row in cur]
            )

        cur.execute(
            """SELECT revision, payload_bytes,
            extract(epoch FROM clock_timestamp() - created_at)
            FROM link_outbox WHERE batch_id IS NULL ORDER BY revision LIMIT %s""",
            (BATCH_PAGES,),
        )
        rows = cur.fetchall()
        if not rows:
            return None
        if (
            not force
            and len(rows) < BATCH_PAGES
            and sum(row[1] for row in rows) < BATCH_BYTES
            and max(row[2] for row in rows) < FLUSH_SECONDS
        ):
            return None
        selected, size = [], 0
        for row in rows:
            if selected and size + row[1] > BATCH_BYTES:
                break
            selected.append(row)
            size += row[1]
        batch_id = str(uuid4())
        cur.execute(
            "INSERT INTO link_archive_batches (batch_id) VALUES (%s) RETURNING created_at",
            (batch_id,),
        )
        created_at = cur.fetchone()[0]
        cur.execute(
            "UPDATE link_outbox SET batch_id = %s WHERE revision = ANY(%s)",
            (batch_id, [row[0] for row in selected]),
        )
        cur.execute(
            "SELECT payload FROM link_outbox WHERE batch_id = %s ORDER BY revision",
            (batch_id,),
        )
        return Batch(batch_id, created_at, [Observation.decode(row[0]) for row in cur])


def acknowledge(batch: Batch) -> None:
    """Called only after verifying both the payload and its R2 commit marker."""
    with transaction() as cur:
        cur.execute(
            """DELETE FROM link_outbox WHERE batch_id = %s
            AND revision = ANY(%s) RETURNING payload_bytes""",
            (batch.batch_id, [record.revision for record in batch.records]),
        )
        size = sum(row[0] for row in cur)
        cur.execute(
            "UPDATE link_archive_state SET pending_bytes = pending_bytes - %s WHERE singleton",
            (size,),
        )
        cur.execute(
            "DELETE FROM link_archive_batches WHERE batch_id = %s", (batch.batch_id,)
        )


def pending_batch_ids() -> set[str]:
    with transaction() as cur:
        cur.execute("SELECT batch_id FROM link_archive_batches")
        return {str(row[0]) for row in cur}
