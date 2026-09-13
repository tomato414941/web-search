"""Resumable export of the frozen pre-cutover graph, without deleting it."""

from datetime import datetime
from itertools import groupby

from web_search_core.urls import get_domain, url_hash
from web_search_postgres.search import get_connection
from web_search_web_model.archive.locks import archive_lock
from web_search_web_model.archive.outbox import Batch, transaction
from web_search_web_model.archive.records import (
    BATCH_BYTES,
    BATCH_PAGES,
    Observation,
    digest,
)
from web_search_web_model.archive.store import ObjectStore, publish_batch
from psycopg2.extras import execute_values


def _save_batch(
    store: ObjectStore, records: list[Observation], started: datetime
) -> None:
    # Content-derived identity makes interrupted export retries idempotent.
    batch_id = "baseline-" + digest(b"".join(record.encode() for record in records))
    publish_batch(store, Batch(batch_id, started, records))
    with transaction() as cur:
        # Match the live writer's lock order: archive state, then URL ledger.
        cur.execute(
            "SELECT singleton FROM link_archive_state WHERE singleton FOR UPDATE"
        )
        discoveries = {
            url for record in records for url in (record.src, *record.outlinks)
        }
        rows = sorted(
            (url_hash(url), url, get_domain(url), int(started.timestamp()))
            for url in discoveries
        )
        execute_values(
            cur,
            """INSERT INTO urls (url_hash, url, domain, created_at)
            SELECT incoming.* FROM (VALUES %s)
                AS incoming (url_hash, url, domain, created_at)
            WHERE NOT EXISTS (
                SELECT 1 FROM urls WHERE urls.url_hash = incoming.url_hash
            )
            ON CONFLICT (url_hash) DO NOTHING""",
            rows,
            page_size=1_000,
        )
        cur.execute(
            """UPDATE link_archive_state SET legacy_last_src = %s,
            legacy_pages = legacy_pages + %s, legacy_edges = legacy_edges + %s
            WHERE singleton""",
            (
                records[-1].src,
                len(records),
                sum(len(record.outlinks) for record in records),
            ),
        )


def export_legacy(store: ObjectStore) -> dict[str, int | bool]:
    # Also prevents a second exporter from advancing the same checkpoint.
    with archive_lock(exporter=True):
        with transaction() as cur:
            cur.execute("""UPDATE link_archive_state
                SET legacy_started_at = coalesce(legacy_started_at, clock_timestamp())
                WHERE singleton RETURNING legacy_started_at, legacy_last_src, legacy_complete""")
            started, last_src, complete = cur.fetchone()
        if not complete:
            con = get_connection()
            try:
                with con.cursor(name="legacy_link_export") as cur:
                    cur.itersize = 10_000
                    cur.execute(
                        "SELECT src, dst FROM legacy_links WHERE (%s::text IS NULL OR src > %s) ORDER BY src, dst",
                        (last_src, last_src),
                    )
                    records, size = [], 0
                    for src, rows in groupby(cur, key=lambda row: row[0]):
                        record = Observation(
                            src,
                            get_domain(src),
                            0,
                            None,
                            sorted({dst for _, dst in rows if dst != src}),
                        )
                        length = len(record.encode())
                        if records and (
                            len(records) >= BATCH_PAGES or size + length > BATCH_BYTES
                        ):
                            _save_batch(store, records, started)
                            records, size = [], 0
                        records.append(record)
                        size += length
                    if records:
                        _save_batch(store, records, started)
                con.rollback()
            finally:
                con.close()
            with transaction() as cur:
                cur.execute(
                    "UPDATE link_archive_state SET legacy_complete = TRUE WHERE singleton"
                )
        with transaction() as cur:
            cur.execute(
                "SELECT legacy_complete, legacy_pages, legacy_edges FROM link_archive_state WHERE singleton"
            )
            complete, pages, edges = cur.fetchone()
        return {"complete": complete, "pages": pages, "edges": edges}
