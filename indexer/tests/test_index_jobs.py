"""Tests for async indexing job queue service."""

from app.core.config import settings
from app.services.index_jobs import IndexJobService


def test_enqueue_and_get_status():
    service = IndexJobService(settings.DB_PATH)

    job_id, created = service.enqueue(
        url="https://example.com",
        title="Title",
        content="Body",
        outlinks=["https://example.com/a"],
    )

    assert created is True
    assert job_id

    status = service.get_job_status(job_id)
    assert status is not None
    assert status["job_id"] == job_id
    assert status["status"] == "pending"
    assert status["retry_count"] == 0


def test_enqueue_is_deduplicated_by_content_hash():
    service = IndexJobService(settings.DB_PATH)

    job_id_1, created_1 = service.enqueue(
        url="https://example.com",
        title="Title-1",
        content="same-content",
        outlinks=[],
    )
    job_id_2, created_2 = service.enqueue(
        url="https://example.com",
        title="Title-2",
        content="same-content",
        outlinks=[],
    )

    assert created_1 is True
    assert created_2 is False
    assert job_id_1 == job_id_2


def test_claim_and_mark_done():
    service = IndexJobService(settings.DB_PATH)
    job_id, _ = service.enqueue(
        url="https://claim.example.com",
        title="Claim",
        content="content",
        outlinks=[],
    )

    jobs = service.claim_jobs(limit=1, lease_seconds=60, worker_id="worker-1")
    assert len(jobs) == 1
    assert jobs[0].job_id == job_id
    assert jobs[0].status == "processing"

    service.mark_done(job_id)
    status = service.get_job_status(job_id)
    assert status is not None
    assert status["status"] == "done"


def test_failure_retries_then_permanent_failure():
    service = IndexJobService(
        settings.DB_PATH,
        max_retries=2,
        retry_base_seconds=0,
        retry_max_seconds=0,
    )
    job_id, _ = service.enqueue(
        url="https://retry.example.com",
        title="Retry",
        content="content",
        outlinks=[],
    )

    first_claim = service.claim_jobs(limit=1, lease_seconds=60, worker_id="worker-1")
    assert first_claim
    service.mark_failure(job_id, "temp error")

    status_after_first = service.get_job_status(job_id)
    assert status_after_first is not None
    assert status_after_first["status"] == "failed_retry"
    assert status_after_first["retry_count"] == 1

    second_claim = service.claim_jobs(limit=1, lease_seconds=60, worker_id="worker-2")
    assert second_claim
    service.mark_failure(job_id, "temp error again")

    status_after_second = service.get_job_status(job_id)
    assert status_after_second is not None
    assert status_after_second["status"] == "failed_permanent"
    assert status_after_second["retry_count"] == 2
