import asyncio
from contextlib import suppress
from types import SimpleNamespace

import pytest

from web_search_indexer import worker


def test_resolve_worker_mode_defaults_to_all():
    assert worker.resolve_worker_mode(["web_search_indexer.worker"]) == "all"


def test_resolve_worker_mode_accepts_explicit_modes():
    assert worker.resolve_worker_mode(["web_search_indexer.worker", "jobs"]) == "jobs"
    assert (
        worker.resolve_worker_mode(["web_search_indexer.worker", "maintenance"])
        == "maintenance"
    )


def test_resolve_worker_mode_rejects_unknown_mode():
    try:
        worker.resolve_worker_mode(["web_search_indexer.worker", "invalid"])
    except ValueError as exc:
        assert "Unsupported worker mode" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported worker mode")


def test_build_task_specs_for_jobs(monkeypatch):
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_WORKERS", 2)

    task_names = [task_name for task_name, _ in worker._build_task_specs("jobs")]

    assert task_names == ["indexer-worker-1", "indexer-worker-2"]


def test_build_task_specs_for_maintenance(monkeypatch):
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_WORKERS", 2)

    task_names = [task_name for task_name, _ in worker._build_task_specs("maintenance")]

    assert task_names == ["job-cleanup"]


def test_build_task_specs_for_all(monkeypatch):
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_WORKERS", 2)

    task_names = [task_name for task_name, _ in worker._build_task_specs("all")]

    assert task_names == [
        "job-cleanup",
        "indexer-worker-1",
        "indexer-worker-2",
    ]


@pytest.mark.asyncio
async def test_index_job_worker_batches_opensearch_before_mark_done(monkeypatch):
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_CONCURRENCY", 1)
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_BATCH_SIZE", 10)
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_LEASE_SEC", 60)
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_POLL_INTERVAL_MS", 50)

    claimed = False
    done_event = asyncio.Event()
    call_log: list[tuple[str, object]] = []

    job = SimpleNamespace(
        job_id="job-1",
        url="https://example.com/page",
        title="Title",
        content="Body",
        outlinks_count=1,
    )
    indexed_page = worker.IndexedPage(
        url=job.url,
        title=job.title,
        content=job.content,
        outlinks_count=1,
    )

    async def fake_index_page(**kwargs):
        call_log.append(("index_page", kwargs["skip_opensearch"]))
        return indexed_page

    async def fake_index_pages_to_opensearch(pages):
        call_log.append(("opensearch", [page.url for page in pages]))
        return len(pages)

    def fake_claim_jobs(limit, lease_seconds, worker_id):
        nonlocal claimed
        if claimed:
            return []
        claimed = True
        return [job]

    def fake_mark_done(job_id, worker_id):
        call_log.append(("mark_done", job_id))
        done_event.set()
        return True

    monkeypatch.setattr(worker.indexer_service, "index_page", fake_index_page)
    monkeypatch.setattr(
        worker.indexer_service,
        "index_pages_to_opensearch",
        fake_index_pages_to_opensearch,
    )
    monkeypatch.setattr(worker.index_job_service, "claim_jobs", fake_claim_jobs)
    monkeypatch.setattr(worker.index_job_service, "mark_done", fake_mark_done)

    task = asyncio.create_task(worker._index_job_worker_loop("worker-1"))
    await asyncio.wait_for(done_event.wait(), timeout=1)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert call_log == [
        ("index_page", True),
        ("opensearch", ["https://example.com/page"]),
        ("mark_done", "job-1"),
    ]


@pytest.mark.asyncio
async def test_index_job_worker_marks_failure_when_opensearch_fails(monkeypatch):
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_CONCURRENCY", 1)
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_BATCH_SIZE", 10)
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_LEASE_SEC", 60)
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_POLL_INTERVAL_MS", 50)

    claimed = False
    failure_event = asyncio.Event()
    call_log: list[tuple[str, object]] = []

    job = SimpleNamespace(
        job_id="job-opensearch-failed",
        url="https://example.com/opensearch-failed",
        title="Title",
        content="Body",
        outlinks_count=0,
    )
    indexed_page = worker.IndexedPage(
        url=job.url,
        title=job.title,
        content=job.content,
        outlinks_count=0,
    )

    async def fake_index_page(**kwargs):
        call_log.append(("index_page", kwargs["skip_opensearch"]))
        return indexed_page

    async def fake_index_pages_to_opensearch(pages):
        call_log.append(("opensearch", [page.url for page in pages]))
        raise RuntimeError("read-only index")

    def fake_claim_jobs(limit, lease_seconds, worker_id):
        nonlocal claimed
        if claimed:
            return []
        claimed = True
        return [job]

    def fake_mark_done(job_id, worker_id):
        raise AssertionError("failed OpenSearch jobs must not be marked done")

    def fake_mark_failure(job_id, error_text, worker_id):
        call_log.append(("mark_failure", job_id))
        assert "OpenSearch indexing failed" in error_text
        failure_event.set()
        return True

    monkeypatch.setattr(worker.indexer_service, "index_page", fake_index_page)
    monkeypatch.setattr(
        worker.indexer_service,
        "index_pages_to_opensearch",
        fake_index_pages_to_opensearch,
    )
    monkeypatch.setattr(worker.index_job_service, "claim_jobs", fake_claim_jobs)
    monkeypatch.setattr(worker.index_job_service, "mark_done", fake_mark_done)
    monkeypatch.setattr(worker.index_job_service, "mark_failure", fake_mark_failure)

    task = asyncio.create_task(worker._index_job_worker_loop("worker-1"))
    await asyncio.wait_for(failure_event.wait(), timeout=1)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert call_log == [
        ("index_page", True),
        ("opensearch", ["https://example.com/opensearch-failed"]),
        ("mark_failure", "job-opensearch-failed"),
    ]


@pytest.mark.asyncio
async def test_index_job_worker_ignores_embedding_flag(monkeypatch):
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_CONCURRENCY", 1)
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_BATCH_SIZE", 10)
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_LEASE_SEC", 60)
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_POLL_INTERVAL_MS", 50)

    claimed = False
    done_event = asyncio.Event()
    call_log: list[tuple[str, object]] = []

    job = SimpleNamespace(
        job_id="job-embed-1",
        url="https://example.com/embed",
        title="Title",
        content="Body",
        outlinks_count=0,
    )
    indexed_page = worker.IndexedPage(
        url=job.url,
        title=job.title,
        content=job.content,
        outlinks_count=0,
    )

    async def fake_index_page(**kwargs):
        assert "skip_embedding" not in kwargs
        call_log.append(("index_page", kwargs["skip_opensearch"]))
        return indexed_page

    async def fake_index_pages_to_opensearch(pages):
        call_log.append(("opensearch", [page.url for page in pages]))
        return len(pages)

    def fake_claim_jobs(limit, lease_seconds, worker_id):
        nonlocal claimed
        if claimed:
            return []
        claimed = True
        return [job]

    def fake_mark_done(job_id, worker_id):
        call_log.append(("mark_done", job_id))
        done_event.set()
        return True

    def fake_mark_failure(job_id, error_text, worker_id):
        call_log.append(("mark_failure", job_id))
        return True

    monkeypatch.setattr(worker.indexer_service, "index_page", fake_index_page)
    monkeypatch.setattr(
        worker.indexer_service,
        "index_pages_to_opensearch",
        fake_index_pages_to_opensearch,
    )
    monkeypatch.setattr(worker.index_job_service, "claim_jobs", fake_claim_jobs)
    monkeypatch.setattr(worker.index_job_service, "mark_done", fake_mark_done)
    monkeypatch.setattr(worker.index_job_service, "mark_failure", fake_mark_failure)

    task = asyncio.create_task(worker._index_job_worker_loop("worker-1"))
    await asyncio.wait_for(done_event.wait(), timeout=1)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert call_log == [
        ("index_page", True),
        ("opensearch", ["https://example.com/embed"]),
        ("mark_done", "job-embed-1"),
    ]
    assert ("mark_failure", "job-embed-1") not in call_log


@pytest.mark.asyncio
async def test_index_job_worker_has_no_embedding_kwargs(monkeypatch):
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_CONCURRENCY", 1)
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_BATCH_SIZE", 10)
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_LEASE_SEC", 60)
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_POLL_INTERVAL_MS", 50)

    claimed = False
    done_event = asyncio.Event()
    call_log: list[tuple[str, object]] = []

    job = SimpleNamespace(
        job_id="job-embed-disabled",
        url="https://example.com/embed-disabled",
        title="Title",
        content="Body",
        outlinks_count=0,
    )
    indexed_page = worker.IndexedPage(
        url=job.url,
        title=job.title,
        content=job.content,
        outlinks_count=0,
    )

    async def fake_index_page(**kwargs):
        assert "skip_embedding" not in kwargs
        call_log.append(("index_page", kwargs["skip_opensearch"]))
        return indexed_page

    async def fake_index_pages_to_opensearch(pages):
        call_log.append(("opensearch", [page.url for page in pages]))
        return len(pages)

    def fake_claim_jobs(limit, lease_seconds, worker_id):
        nonlocal claimed
        if claimed:
            return []
        claimed = True
        return [job]

    def fake_mark_done(job_id, worker_id):
        call_log.append(("mark_done", job_id))
        done_event.set()
        return True

    monkeypatch.setattr(worker.indexer_service, "index_page", fake_index_page)
    monkeypatch.setattr(
        worker.indexer_service,
        "index_pages_to_opensearch",
        fake_index_pages_to_opensearch,
    )
    monkeypatch.setattr(worker.index_job_service, "claim_jobs", fake_claim_jobs)
    monkeypatch.setattr(worker.index_job_service, "mark_done", fake_mark_done)

    task = asyncio.create_task(worker._index_job_worker_loop("worker-1"))
    await asyncio.wait_for(done_event.wait(), timeout=1)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert call_log == [
        ("index_page", True),
        ("opensearch", ["https://example.com/embed-disabled"]),
        ("mark_done", "job-embed-disabled"),
    ]
