"""Tests for failed_permanent job visibility and retry."""

from app.api.routes.indexer import index_job_service
from app.core.config import settings
from app.services.index_jobs import STATUS_FAILED_PERMANENT, STATUS_PENDING
from shared.postgres.search import get_connection, sql_placeholder

API_KEY_HEADER = {"X-API-Key": settings.INDEXER_API_KEY}


def _force_fail_job(job_id: str, db_path: str = "test_indexer.db"):
    """Set a job to failed_permanent status for testing."""
    ph = sql_placeholder()
    con = get_connection(db_path)
    cur = con.cursor()
    cur.execute(
        f"UPDATE index_jobs SET status = {ph}, retry_count = 5, "
        f"last_error = {ph} WHERE job_id = {ph}",
        (STATUS_FAILED_PERMANENT, "test error", job_id),
    )
    con.commit()
    cur.close()
    con.close()


class TestGetFailedPermanentJobs:
    def test_empty_when_no_failures(self):
        jobs = index_job_service.get_failed_permanent_jobs()
        assert jobs == []

    def test_returns_only_failed_permanent(self):
        job_id, _ = index_job_service.enqueue(
            url="http://fail.example.com",
            title="Fail",
            content="Content",
            outlinks=[],
        )
        _force_fail_job(job_id)

        jobs = index_job_service.get_failed_permanent_jobs()
        assert len(jobs) == 1
        assert jobs[0]["job_id"] == job_id
        assert jobs[0]["url"] == "http://fail.example.com"
        assert jobs[0]["last_error"] == "test error"


class TestRetryFailedJob:
    def test_resets_to_pending(self):
        job_id, _ = index_job_service.enqueue(
            url="http://retry.example.com",
            title="Retry",
            content="Content",
            outlinks=[],
        )
        _force_fail_job(job_id)

        success = index_job_service.retry_failed_job(job_id)
        assert success is True

        status = index_job_service.get_job_status(job_id)
        assert status["status"] == STATUS_PENDING
        assert status["retry_count"] == 0

    def test_returns_false_for_non_failed_job(self):
        job_id, _ = index_job_service.enqueue(
            url="http://pending.example.com",
            title="Pending",
            content="Content2",
            outlinks=[],
        )
        success = index_job_service.retry_failed_job(job_id)
        assert success is False


class TestFailedJobsAPI:
    def test_get_failed_jobs_requires_api_key(self, test_client):
        resp = test_client.get("/api/v1/indexer/jobs/failed")
        assert resp.status_code == 422

    def test_get_failed_jobs_with_valid_key(self, test_client):
        resp = test_client.get(
            "/api/v1/indexer/jobs/failed",
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert isinstance(data["jobs"], list)

    def test_retry_nonexistent_job(self, test_client):
        resp = test_client.post(
            "/api/v1/indexer/jobs/nonexistent-id/retry",
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 404

    def test_retry_failed_job_via_api(self, test_client):
        job_id, _ = index_job_service.enqueue(
            url="http://api-retry.example.com",
            title="API Retry",
            content="API Content",
            outlinks=[],
        )
        _force_fail_job(job_id)

        resp = test_client.post(
            f"/api/v1/indexer/jobs/{job_id}/retry",
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
