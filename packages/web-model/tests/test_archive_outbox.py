import pytest

from web_search_web_model.archive import outbox
from web_search_web_model.archive.outbox import (
    ArchiveFull,
    append_observation,
    claim_batch,
    status,
    transaction,
)
from web_search_web_model.archive.records import PREFIX, Observation
from web_search_web_model.archive.worker import flush_once


def append(src="https://a.example/page", outlinks=None):
    with transaction() as cur:
        append_observation(cur, src, "a.example", outlinks or [])


def test_flush_waits_for_oldest_record_and_acks_verified_objects(object_store):
    append()
    assert flush_once(object_store) == 0
    assert object_store.client.objects == {}
    with transaction() as cur:
        cur.execute(
            "UPDATE link_outbox SET created_at = clock_timestamp() - interval '6 minutes'"
        )
    assert flush_once(object_store) == 1
    assert status()["pending_pages"] == status()["pending_bytes"] == 0
    assert len(object_store.client.objects) == 2
    assert all(condition == "*" for _, _, condition in object_store.client.puts)


def test_failed_readback_keeps_exact_batch_for_retry(object_store, monkeypatch):
    append()
    original = object_store.get
    failed = False

    def fail_once(key):
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("connection lost after PUT")
        return original(key)

    monkeypatch.setattr(object_store, "get", fail_once)
    with pytest.raises(RuntimeError):
        flush_once(object_store, force=True)
    first = claim_batch(force=True)
    append("https://later.example/page")
    assert claim_batch(force=True) == first
    assert flush_once(object_store, force=True) == 1
    assert status()["pending_pages"] == 1
    assert len(object_store.client.objects) == 2
    assert flush_once(object_store, force=True) == 1
    assert status()["pending_pages"] == 0


def test_commit_written_before_ack_can_be_retried(object_store, monkeypatch):
    from web_search_web_model.archive import worker

    append()
    acknowledge = worker.acknowledge
    monkeypatch.setattr(
        worker,
        "acknowledge",
        lambda batch: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    with pytest.raises(RuntimeError):
        flush_once(object_store, force=True)
    assert len(object_store.client.objects) == 2
    assert status()["pending_pages"] == 1
    monkeypatch.setattr(worker, "acknowledge", acknowledge)
    assert flush_once(object_store, force=True) == 1
    assert len(object_store.client.objects) == 2


def test_batch_size_bounds_and_age_flush(monkeypatch):
    monkeypatch.setattr(outbox, "BATCH_PAGES", 2)
    append("https://a.example/1")
    append("https://a.example/2")
    append("https://a.example/3")
    batch = claim_batch()
    assert len(batch.records) == 2
    outbox.acknowledge(batch)
    assert claim_batch() is None
    assert len(claim_batch(force=True).records) == 1


def test_capacity_rejects_whole_transaction():
    with transaction() as cur:
        cur.execute(
            "UPDATE link_archive_state SET pending_bytes = %s",
            (outbox.pending_limit(),),
        )
    assert not outbox.has_capacity()
    with pytest.raises(ArchiveFull):
        append()
    assert status()["pending_pages"] == 0


def test_byte_limit_flushes_without_splitting_a_page(monkeypatch):
    append("https://a.example/1")
    append("https://a.example/2")
    with transaction() as cur:
        cur.execute("SELECT sum(payload_bytes) FROM link_outbox")
        size = cur.fetchone()[0]
    monkeypatch.setattr(outbox, "BATCH_BYTES", size - 1)
    batch = claim_batch()
    assert len(batch.records) == 1
    assert len(batch.records[0].encode()) < size - 1
    outbox.acknowledge(batch)
    assert status()["pending_pages"] == 1


def test_two_uploaders_do_not_race_the_same_batch(object_store):
    from concurrent.futures import ThreadPoolExecutor

    append()
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(flush_once, object_store, force=True) for _ in range(2)
        ]
        assert sorted(future.result(timeout=10) for future in futures) == [0, 1]
    assert status()["pending_pages"] == status()["pending_bytes"] == 0
    assert len(object_store.client.objects) == 2


def test_missing_lower_revision_is_not_skipped(object_store):
    with transaction() as cur:
        cur.execute("SELECT nextval('link_observation_revision')")
        reserved = cur.fetchone()[0]
    append()
    assert flush_once(object_store, force=True) == 1
    # The lower sequence allocation commits after the higher one was uploaded.
    record = Observation(
        "https://late.example/", "late.example", reserved, "2026-01-01T00:00:00Z", []
    )
    payload = record.encode()
    with transaction() as cur:
        cur.execute(
            "INSERT INTO link_outbox (revision, payload, payload_bytes) VALUES (%s, %s, %s)",
            (reserved, payload.decode(), len(payload)),
        )
        cur.execute(
            "UPDATE link_archive_state SET pending_bytes = pending_bytes + %s",
            (len(payload),),
        )
    assert flush_once(object_store, force=True) == 1
    assert (
        len(
            [
                key
                for key in object_store.client.objects
                if key.startswith(f"{PREFIX}commits/")
            ]
        )
        == 2
    )


def test_r2_conflicting_batch_is_not_acked(object_store):
    from web_search_web_model.archive.store import ArchiveConflict

    append()
    batch = claim_batch(force=True)
    key = f"{PREFIX}updates/{batch.created_at:%Y/%m/%d}/{batch.batch_id}.jsonl.gz"
    object_store.put(key, b"unexpected contents")
    with pytest.raises(ArchiveConflict):
        flush_once(object_store, force=True)
    assert status()["pending_pages"] == 1


def test_s3_put_uses_conditional_header_with_current_sdk():
    from io import BytesIO
    import boto3
    from botocore.response import StreamingBody
    from botocore.stub import Stubber
    from web_search_web_model.archive.store import ObjectStore

    client = boto3.client(
        "s3", region_name="auto", aws_access_key_id="test", aws_secret_access_key="test"
    )
    store = ObjectStore(client, "test-bucket")
    with Stubber(client) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "test-bucket",
                "Key": f"{PREFIX}test",
                "Body": b"test",
                "IfNoneMatch": "*",
            },
        )
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(BytesIO(b"test"), 4), "ETag": '"tag"'},
            {"Bucket": "test-bucket", "Key": f"{PREFIX}test"},
        )
        store.put(f"{PREFIX}test", b"test")
        stub.assert_no_pending_responses()
