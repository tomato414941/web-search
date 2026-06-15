"""Tests for async indexing job queue service."""

from web_search_indexer.services.index_jobs import IndexJobService
from web_search_postgres.search import get_connection, sql_placeholder


def _job_state(job_id: str) -> dict[str, object]:
    ph = sql_placeholder()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT job_id, status, retry_count
            FROM index_jobs
            WHERE job_id = {ph}
            """,
            (job_id,),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()
    assert row is not None
    return {
        "job_id": str(row[0]),
        "status": str(row[1]),
        "retry_count": int(row[2]),
    }


def test_enqueue_queues_pending_job():
    service = IndexJobService()

    job_id, created = service.enqueue(
        url="https://example.com",
        title="Title",
        content="Body",
    )

    assert created is True
    assert job_id

    status = _job_state(job_id)
    assert status["job_id"] == job_id
    assert status["status"] == "pending"
    assert status["retry_count"] == 0


def test_enqueue_is_deduplicated_by_active_url():
    service = IndexJobService()

    job_id_1, created_1 = service.enqueue(
        url="https://example.com",
        title="Title-1",
        content="first-content",
    )
    job_id_2, created_2 = service.enqueue(
        url="https://example.com",
        title="Title-2",
        content="different-content",
    )

    assert created_1 is True
    assert created_2 is False
    assert job_id_1 == job_id_2


def test_enqueue_allows_same_url_after_done():
    service = IndexJobService()

    job_id_1, created_1 = service.enqueue(
        url="https://done-again.example.com",
        title="Title-1",
        content="first-content",
    )
    assert created_1 is True

    service.claim_jobs(limit=1, lease_seconds=60, worker_id="worker-1")
    assert service.mark_done(job_id_1, worker_id="worker-1") is True

    job_id_2, created_2 = service.enqueue(
        url="https://done-again.example.com",
        title="Title-2",
        content="second-content",
    )

    assert created_2 is True
    assert job_id_2 != job_id_1


def test_enqueue_allows_same_url_after_permanent_failure():
    service = IndexJobService(
        max_retries=1,
        retry_base_seconds=0,
        retry_max_seconds=0,
    )

    job_id_1, created_1 = service.enqueue(
        url="https://failed-again.example.com",
        title="Title-1",
        content="first-content",
    )
    assert created_1 is True

    service.claim_jobs(limit=1, lease_seconds=60, worker_id="worker-1")
    assert service.mark_failure(job_id_1, "permanent", worker_id="worker-1") is True

    status = _job_state(job_id_1)
    assert status["status"] == "failed_permanent"

    job_id_2, created_2 = service.enqueue(
        url="https://failed-again.example.com",
        title="Title-2",
        content="second-content",
    )

    assert created_2 is True
    assert job_id_2 != job_id_1


def test_claim_and_mark_done():
    service = IndexJobService()
    job_id, _ = service.enqueue(
        url="https://claim.example.com",
        title="Claim",
        content="content",
    )

    jobs = service.claim_jobs(limit=1, lease_seconds=60, worker_id="worker-1")
    assert len(jobs) == 1
    assert jobs[0].job_id == job_id
    assert jobs[0].status == "processing"

    service.mark_done(job_id)
    status = _job_state(job_id)
    assert status["status"] == "done"


def test_failure_retries_then_permanent_failure():
    service = IndexJobService(
        max_retries=2,
        retry_base_seconds=0,
        retry_max_seconds=0,
    )
    job_id, _ = service.enqueue(
        url="https://retry.example.com",
        title="Retry",
        content="content",
    )

    first_claim = service.claim_jobs(limit=1, lease_seconds=60, worker_id="worker-1")
    assert first_claim
    service.mark_failure(job_id, "temp error")

    status_after_first = _job_state(job_id)
    assert status_after_first["status"] == "failed_retry"
    assert status_after_first["retry_count"] == 1

    second_claim = service.claim_jobs(limit=1, lease_seconds=60, worker_id="worker-2")
    assert second_claim
    service.mark_failure(job_id, "temp error again")

    status_after_second = _job_state(job_id)
    assert status_after_second["status"] == "failed_permanent"
    assert status_after_second["retry_count"] == 2


def test_mark_done_cas_rejects_wrong_worker():
    """mark_done with worker_id should reject if worker doesn't own the job."""
    service = IndexJobService()
    job_id, _ = service.enqueue(
        url="https://cas-done.example.com",
        title="CAS",
        content="cas-test-done",
    )
    service.claim_jobs(limit=1, lease_seconds=60, worker_id="worker-A")

    # Wrong worker cannot mark done
    result = service.mark_done(job_id, worker_id="worker-B")
    assert result is False

    status = _job_state(job_id)
    assert status["status"] == "processing"

    # Correct worker succeeds
    result = service.mark_done(job_id, worker_id="worker-A")
    assert result is True

    status = _job_state(job_id)
    assert status["status"] == "done"


def test_mark_failure_cas_rejects_wrong_worker():
    """mark_failure with worker_id should reject if worker doesn't own the job."""
    service = IndexJobService()
    job_id, _ = service.enqueue(
        url="https://cas-fail.example.com",
        title="CAS",
        content="cas-test-fail",
    )
    service.claim_jobs(limit=1, lease_seconds=60, worker_id="worker-A")

    # Wrong worker cannot mark failure
    result = service.mark_failure(job_id, "error", worker_id="worker-B")
    assert result is False

    status = _job_state(job_id)
    assert status["status"] == "processing"

    # Correct worker succeeds
    result = service.mark_failure(job_id, "real error", worker_id="worker-A")
    assert result is True

    status = _job_state(job_id)
    assert status["status"] == "failed_retry"
