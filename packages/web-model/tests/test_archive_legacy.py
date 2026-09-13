import pytest
from psycopg2.errors import RaiseException

from web_search_core.urls import url_hash
from web_search_web_model.archive import legacy
from web_search_web_model.archive.outbox import append_observation, transaction
from web_search_web_model.archive.snapshots import iter_latest
from web_search_web_model.archive.worker import flush_once


def seed():
    with transaction() as cur:
        cur.execute("ALTER TABLE legacy_links DISABLE TRIGGER freeze_legacy_links")
        cur.executemany(
            "INSERT INTO legacy_links (src, dst) VALUES (%s, %s)",
            [
                ("https://a.example/", "https://old.example/"),
                ("https://b.example/", "https://keep.example/"),
            ],
        )
        cur.execute("ALTER TABLE legacy_links ENABLE TRIGGER freeze_legacy_links")


def test_legacy_export_is_resumable_and_never_overrides_new_observations(
    object_store, monkeypatch
):
    seed()
    monkeypatch.setattr(legacy, "BATCH_PAGES", 1)
    publish = legacy.publish_batch
    calls = 0

    def fail_second(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("R2 unavailable")
        return publish(*args)

    monkeypatch.setattr(legacy, "publish_batch", fail_second)
    with pytest.raises(RuntimeError):
        legacy.export_legacy(object_store)
    with transaction() as cur:
        cur.execute(
            "SELECT legacy_pages, legacy_last_src, legacy_complete FROM link_archive_state"
        )
        assert cur.fetchone() == (1, "https://a.example/", False)
        append_observation(cur, "https://a.example/", "a.example", [])
    flush_once(object_store, force=True)
    result = legacy.export_legacy(object_store)
    assert result == {"complete": True, "pages": 2, "edges": 2}
    assert legacy.export_legacy(object_store) == result
    pages = {page.src: page for page in iter_latest(object_store)}
    assert pages["https://a.example/"].outlinks == []
    assert pages["https://a.example/"].revision > 0
    assert pages["https://b.example/"].outlinks == ["https://keep.example/"]
    assert pages["https://b.example/"].revision == 0
    assert pages["https://b.example/"].observed_at is None
    with transaction() as cur:
        cur.execute("SELECT count(*) FROM legacy_links")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM urls")
        assert cur.fetchone()[0] == 4


def test_legacy_table_rejects_new_writes():
    with pytest.raises(RaiseException, match="frozen"):
        with transaction() as cur:
            cur.execute("INSERT INTO legacy_links VALUES ('a', 'b')")


def test_export_preserves_existing_discoveries_and_registers_missing_urls(object_store):
    seed()
    with transaction() as cur:
        cur.execute(
            "INSERT INTO urls (url_hash, url, domain, created_at) VALUES (%s, %s, %s, %s)",
            (
                url_hash("https://old.example/"),
                "https://old.example/",
                "old.example",
                123,
            ),
        )

    assert legacy.export_legacy(object_store) == {
        "complete": True,
        "pages": 2,
        "edges": 2,
    }
    with transaction() as cur:
        cur.execute("SELECT url, created_at FROM urls ORDER BY url")
        rows = dict(cur.fetchall())
    assert set(rows) == {
        "https://a.example/",
        "https://b.example/",
        "https://old.example/",
        "https://keep.example/",
    }
    assert rows["https://old.example/"] == 123
    assert all(
        created > 123 for url, created in rows.items() if url != "https://old.example/"
    )
