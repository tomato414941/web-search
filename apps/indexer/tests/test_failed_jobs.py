"""Tests for failed_permanent job visibility."""

from web_search_indexer.core.config import settings
from web_search_indexer.services.index_job_container import index_job_service
from web_search_indexer.services.index_jobs import (
    STATUS_FAILED_PERMANENT,
)
from web_search_postgres.search import get_connection, sql_placeholder

API_KEY_HEADER = {"X-API-Key": settings.INDEXER_API_KEY}


def _force_fail_job(job_id: str):
    """Set a job to failed_permanent status for testing."""
    ph = sql_placeholder()
    con = get_connection()
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
