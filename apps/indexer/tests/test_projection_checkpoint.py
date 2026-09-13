import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from web_search_indexer.cli import rebuild_search_projection as rebuild
from web_search_indexer.cli.projection_checkpoint import (
    ProjectionCheckpoint,
    ProjectionProgress,
)


@pytest.fixture
def rebuild_run(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@db/websearch")
    state = SimpleNamespace(
        uuid="original-index",
        path=tmp_path / "progress.json",
        fetched=[],
        attempts=[],
        indexed={},
        fail_batch=None,
        partial=False,
    )
    client = SimpleNamespace(
        indices=SimpleNamespace(
            get_settings=lambda **kwargs: {
                "hybrid": {"settings": {"index": {"uuid": state.uuid}}}
            }
        )
    )
    rows = [
        ("https://example.com/a", "A", "First document"),
        ("https://example.com/b", "B", "Second document"),
        ("https://example.com/c", "C", "Third document"),
    ]

    def fetch(*, limit, last_url):
        state.fetched.append(last_url)
        return [row for row in rows if last_url is None or row[0] > last_url][:limit]

    def bulk(client, documents, **kwargs):
        urls = [doc["url"] for doc in documents]
        state.attempts.append(urls)
        if len(state.attempts) == state.fail_batch:
            if state.partial:
                state.indexed[documents[0]["url"]] = documents[0]
                return len(documents) - 1
            raise RuntimeError("OpenSearch unavailable")
        state.indexed.update((doc["url"], doc) for doc in documents)
        return len(documents)

    monkeypatch.setattr(rebuild, "get_client", lambda url: client)
    monkeypatch.setattr(rebuild, "ensure_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(rebuild, "bulk_index", bulk)
    monkeypatch.setattr(
        rebuild.DocumentRepository, "count_documents", staticmethod(lambda: len(rows))
    )
    monkeypatch.setattr(
        rebuild.DocumentRepository,
        "fetch_documents_for_opensearch_after_url",
        staticmethod(fetch),
    )
    state.run = lambda **kwargs: rebuild.rebuild_search_projection(
        index_name="hybrid", checkpoint_file=state.path, **kwargs
    )
    return state


@pytest.mark.parametrize("partial", [False, True])
def test_failed_bulk_resumes_after_last_successful_batch(rebuild_run, partial):
    state = rebuild_run
    state.fail_batch = 2
    state.partial = partial
    with pytest.raises(RuntimeError):
        state.run(batch_size=1)

    checkpoint = json.loads(state.path.read_text())
    assert checkpoint["progress"] == {
        "last_url": "https://example.com/a",
        "scanned": 1,
        "indexed": 1,
        "complete": False,
    }
    assert "secret" not in state.path.read_text()
    assert state.path.stat().st_mode & 0o777 == 0o600

    state.fail_batch = None
    state.run(batch_size=2)

    assert state.attempts[-1] == ["https://example.com/b", "https://example.com/c"]
    assert len(state.indexed) == 3
    checkpoint = json.loads(state.path.read_text())
    assert checkpoint["progress"]["complete"] is True
    assert checkpoint["progress"]["scanned"] == 3
    assert checkpoint["progress"]["indexed"] == 3
    fetched = list(state.fetched)
    state.run()
    assert state.fetched == fetched


def test_bounded_runs_resume_without_reprocessing_previous_rows(rebuild_run):
    state = rebuild_run
    state.run(max_documents=1)
    state.run(max_documents=1)
    assert state.attempts == [
        ["https://example.com/a"],
        ["https://example.com/b"],
    ]
    assert json.loads(state.path.read_text())["progress"]["complete"] is False
    state.run()
    assert state.attempts[-1] == ["https://example.com/c"]


@pytest.mark.parametrize("different_source", [False, True])
def test_checkpoint_rejects_recreated_index_or_different_database(
    rebuild_run, monkeypatch, different_source
):
    state = rebuild_run
    state.run(max_documents=1)
    before = state.path.read_bytes()
    if different_source:
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@db/another")
    else:
        state.uuid = "replacement-index"
    with pytest.raises(ValueError, match="does not match"):
        state.run()
    assert len(state.attempts) == 1
    assert state.path.read_bytes() == before


def test_checkpoint_lock_prevents_concurrent_rebuilds(tmp_path):
    path = tmp_path / "progress.json"
    with ProjectionCheckpoint(path):
        with pytest.raises(BlockingIOError):
            with ProjectionCheckpoint(path):
                pytest.fail("Concurrent rebuild acquired the same checkpoint")
    with ProjectionCheckpoint(path):
        pass


def test_failed_checkpoint_replace_keeps_previous_progress(tmp_path, monkeypatch):
    from web_search_indexer.cli import projection_checkpoint

    path = tmp_path / "progress.json"
    with ProjectionCheckpoint(path) as checkpoint:
        checkpoint.save({}, ProjectionProgress())
        before = path.read_bytes()

        def fail_replace(source, destination):
            raise OSError("Cannot replace checkpoint")

        monkeypatch.setattr(projection_checkpoint.os, "replace", fail_replace)
        with pytest.raises(OSError):
            checkpoint.save({}, ProjectionProgress("https://example.com/a", 1, 1))
        assert path.read_bytes() == before
        assert sorted(item.name for item in Path(tmp_path).iterdir()) == [
            "progress.json",
            "progress.json.lock",
        ]
