from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from web_search_web_model.archive.outbox import Batch, transaction
from web_search_web_model.archive.records import PREFIX, Observation
from web_search_web_model.archive.snapshots import collect, compact, iter_latest
from web_search_web_model.archive.store import (
    ArchiveConflict,
    publish_batch,
    read_current,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def publish(store, records, *, now=START, batch_id=None):
    return publish_batch(store, Batch(batch_id or str(uuid4()), now, records))


def record(src="https://a.example/", revision=1, outlinks=None):
    return Observation(
        src, src.split("/")[2], revision, "2026-01-01T00:00:00Z", outlinks or []
    )


def test_latest_replacement_empty_lists_and_late_arrivals(object_store):
    publish(
        object_store,
        [
            record(revision=1, outlinks=["https://old.example/"]),
            record("https://b.example/", outlinks=["https://keep.example/"]),
        ],
    )
    first = compact(object_store, now=START)
    frozen = read_current(object_store)[0]["manifest_key"]
    publish(object_store, [record(revision=3)])
    publish(object_store, [record(revision=2, outlinks=["https://stale.example/"])])
    publish(object_store, [record(revision=3)])
    pages = {row.src: row for row in iter_latest(object_store)}
    assert pages["https://a.example/"].outlinks == []
    assert pages["https://a.example/"].revision == 3
    assert pages["https://b.example/"].outlinks == ["https://keep.example/"]
    assert first["pages"] == first["edges"] == 2
    second = compact(object_store, now=START + timedelta(days=1))
    assert second["pages"] == 2 and second["edges"] == 1
    assert list(iter_latest(object_store, src="https://a.example/"))[0].outlinks == []
    assert list(
        iter_latest(object_store, src="https://a.example/", manifest_key=frozen)
    )[0].outlinks == ["https://old.example/"]


def test_same_revision_different_payload_leaves_current_unchanged(object_store):
    publish(object_store, [record()])
    compact(object_store, now=START)
    current = read_current(object_store)
    publish(object_store, [record(outlinks=["https://conflict.example/"])])
    with pytest.raises(ArchiveConflict, match="different observations"):
        compact(object_store, now=START)
    assert read_current(object_store) == current


def test_missing_or_corrupt_update_never_publishes_snapshot(object_store):
    manifest = publish(object_store, [record()])
    object_store.client.objects[manifest["data_key"]] = (b"corrupt", '"etag"', START)
    with pytest.raises(ArchiveConflict, match="checksum"):
        compact(object_store, now=START)
    assert read_current(object_store) == (None, None)


def test_pointer_compare_and_swap_rejects_stale_publication(object_store):
    compact(object_store, now=START)
    current, etag = read_current(object_store)
    compact(object_store, now=START + timedelta(days=1))
    with pytest.raises(ArchiveConflict):
        object_store.put_json(f"{PREFIX}current.json", current, etag=etag)
    assert read_current(object_store)[0] != current


def test_collection_requires_both_snapshots_and_respects_pending_batches(object_store):
    batch_id = str(uuid4())
    initial = publish(object_store, [record()], batch_id=batch_id)
    compact(object_store, now=START)
    second = publish(object_store, [record(revision=2)], now=START + timedelta(days=1))
    compact(object_store, now=START + timedelta(days=1))
    with transaction() as cur:
        cur.execute(
            "INSERT INTO link_archive_batches (batch_id) VALUES (%s)", (batch_id,)
        )
    collect(object_store, now=START + timedelta(days=3))
    assert initial["data_key"] in object_store.client.objects
    assert second["data_key"] in object_store.client.objects
    with transaction() as cur:
        cur.execute("DELETE FROM link_archive_batches")
    collect(object_store, now=START + timedelta(days=3))
    assert initial["data_key"] not in object_store.client.objects
    assert second["data_key"] in object_store.client.objects
    compact(object_store, now=START + timedelta(days=3))
    collect(object_store, now=START + timedelta(days=5))
    assert second["data_key"] not in object_store.client.objects
    assert list(iter_latest(object_store))[0].revision == 2
    assert (
        len(
            [
                key
                for key in object_store.client.objects
                if key.endswith("/manifest.json")
            ]
        )
        == 2
    )


def test_active_reader_pins_files_against_collection(object_store):
    import os
    import psycopg2

    publish(object_store, [record()])
    reader = iter_latest(object_store)
    assert next(reader).src == "https://a.example/"
    con = psycopg2.connect(os.environ["DATABASE_URL"])
    con.autocommit = True
    try:
        with con.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(712043, 3)")
            assert cur.fetchone()[0] is False
            reader.close()
            cur.execute("SELECT pg_try_advisory_lock(712043, 3)")
            assert cur.fetchone()[0] is True
    finally:
        reader.close()
        con.close()


def test_orphan_collection_works_before_first_successful_snapshot(object_store):
    committed = publish(object_store, [record()])
    abandoned = f"{PREFIX}snapshots/abandoned/shard=aa/part-00000.parquet"
    orphan = f"{PREFIX}updates/2026/01/01/abandoned.jsonl.gz"
    object_store.put(abandoned, b"incomplete snapshot")
    object_store.put(orphan, b"uncommitted update")
    assert collect(object_store, now=START + timedelta(hours=12)) == 0
    assert collect(object_store, now=START + timedelta(days=2)) == 2
    assert committed["data_key"] in object_store.client.objects
    assert list(iter_latest(object_store))[0].revision == 1


def test_failed_snapshot_upload_never_changes_current(object_store, monkeypatch):
    publish(object_store, [record()])
    compact(object_store, now=START)
    current = read_current(object_store)
    publish(object_store, [record(revision=2)])

    def fail(*args):
        raise RuntimeError("snapshot upload interrupted")

    monkeypatch.setattr(object_store, "put_file", fail)
    with pytest.raises(RuntimeError):
        compact(object_store, now=START + timedelta(days=1))
    assert read_current(object_store) == current
    assert list(iter_latest(object_store))[0].revision == 2
