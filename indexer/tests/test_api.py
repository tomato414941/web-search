"""Test Indexer API security and async queue behavior."""

import asyncio
from unittest.mock import patch

import pytest

from app.core.config import settings
from shared.core import background as background_module


class TestIndexerAPIAuth:
    """Test indexer API authentication and security."""

    def test_index_page_requires_api_key(self, test_client):
        response = test_client.post(
            "/api/v1/indexer/page",
            json={
                "url": "https://example.com",
                "title": "Test",
                "content": "Test content",
            },
        )
        assert response.status_code == 422

    def test_index_page_with_invalid_api_key(self, test_client):
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": "wrong-key"},
            json={
                "url": "https://example.com",
                "title": "Test",
                "content": "Test content",
            },
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_index_page_with_valid_api_key(self, test_client):
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={
                "url": "https://example.com",
                "title": "Test",
                "content": "Test content",
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert data["ok"] is True
        assert data["queued"] is True
        assert data["job_id"]
        assert data["url"].rstrip("/") == "https://example.com"

    def test_index_page_with_empty_url(self, test_client):
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "", "title": "Test", "content": "Test content"},
        )
        assert response.status_code == 422

    def test_index_page_with_invalid_url(self, test_client):
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "not-a-url", "title": "Test", "content": "Test content"},
        )
        assert response.status_code == 422

    def test_index_page_with_missing_fields(self, test_client):
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "https://example.com", "content": "Test content"},
        )
        assert response.status_code == 422

        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "https://example.com", "title": "Test"},
        )
        assert response.status_code == 422

    def test_index_page_with_empty_content(self, test_client):
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "https://example.com", "title": "Test", "content": ""},
        )
        assert response.status_code in [202, 400]

    def test_index_page_handles_queue_errors_gracefully(self, test_client):
        with patch("app.api.routes.indexer.index_job_service.enqueue") as mock_enqueue:
            mock_enqueue.side_effect = Exception("Database connection failed")

            response = test_client.post(
                "/api/v1/indexer/page",
                headers={"X-API-Key": settings.INDEXER_API_KEY},
                json={"url": "https://example.com", "title": "Test", "content": "Test"},
            )
            assert response.status_code == 500
            assert "detail" in response.json()

    def test_index_page_with_very_long_content(self, test_client):
        long_content = "x" * 100000
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={
                "url": "https://example.com",
                "title": "Test",
                "content": long_content,
            },
        )
        assert response.status_code in [202, 400, 413]

    def test_index_page_with_special_characters(self, test_client):
        special_content = (
            "Test with émojis 🎉 and 特殊文字 <script>alert('xss')</script>"
        )
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={
                "url": "https://example.com",
                "title": "Special chars",
                "content": special_content,
            },
        )
        assert response.status_code == 202
        assert response.json()["ok"] is True


class TestIndexerAPIValidation:
    """Test input validation for indexer API."""

    def test_rejects_javascript_protocol(self, test_client):
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={
                "url": "javascript:alert('xss')",
                "title": "Test",
                "content": "Test",
            },
        )
        assert response.status_code == 422

    def test_accepts_http_and_https_only(self, test_client):
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "http://example.com", "title": "Test", "content": "Test"},
        )
        assert response.status_code == 202

        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "https://example.com", "title": "Test", "content": "Test"},
        )
        assert response.status_code == 202

    def test_duplicate_payload_is_deduplicated(self, test_client):
        url = "https://unique-test.example.com"

        response1 = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": url, "title": "First Title", "content": "same content"},
        )
        assert response1.status_code == 202

        response2 = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": url, "title": "Different title", "content": "same content"},
        )
        assert response2.status_code == 202

        body1 = response1.json()
        body2 = response2.json()
        assert body1["job_id"] == body2["job_id"]
        assert body2["deduplicated"] is True

    def test_different_content_creates_different_job(self, test_client):
        url = "https://reindex.example.com"

        response1 = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": url, "title": "Title", "content": "first"},
        )
        response2 = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": url, "title": "Title", "content": "second"},
        )

        assert response1.status_code == 202
        assert response2.status_code == 202
        assert response1.json()["job_id"] != response2.json()["job_id"]

    def test_get_job_status(self, test_client):
        enqueue_resp = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={
                "url": "https://status.example.com",
                "title": "Status",
                "content": "status test",
            },
        )
        assert enqueue_resp.status_code == 202
        job_id = enqueue_resp.json()["job_id"]

        status_resp = test_client.get(
            f"/api/v1/indexer/jobs/{job_id}",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
        )
        assert status_resp.status_code == 200
        body = status_resp.json()
        assert body["ok"] is True
        assert body["job_id"] == job_id
        assert body["status"] in {
            "pending",
            "processing",
            "done",
            "failed_retry",
            "failed_permanent",
        }

    def test_get_job_status_not_found(self, test_client):
        response = test_client.get(
            "/api/v1/indexer/jobs/not-found",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
        )
        assert response.status_code == 404


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_root_health_check(self, test_client):
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_indexer_stats_contains_job_stats(self, test_client):
        response = test_client.get(
            "/api/v1/indexer/stats",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert "pending_jobs" in body
        assert "processing_jobs" in body
        assert "failed_permanent_jobs" in body
        assert "oldest_pending_seconds" in body

    def test_indexer_stats_uses_short_ttl_cache(self, test_client):
        from app.api.routes import indexer as route_module

        route_module._stats_cache["data"] = None
        route_module._stats_cache["expires"] = 0.0

        queue_stats = {
            "pending_jobs": 3,
            "processing_jobs": 1,
            "done_jobs": 9,
            "failed_permanent_jobs": 0,
            "total_jobs": 13,
            "oldest_pending_seconds": 12,
        }

        with (
            patch(
                "app.api.routes.indexer.indexer_service.get_index_stats"
            ) as mock_stats,
            patch(
                "app.api.routes.indexer.index_job_service.get_queue_stats"
            ) as mock_queue,
        ):
            mock_stats.return_value = {"total": 42}
            mock_queue.return_value = queue_stats

            first = test_client.get(
                "/api/v1/indexer/stats",
                headers={"X-API-Key": settings.INDEXER_API_KEY},
            )
            first_stats_calls = mock_stats.call_count
            first_queue_calls = mock_queue.call_count
            second = test_client.get(
                "/api/v1/indexer/stats",
                headers={"X-API-Key": settings.INDEXER_API_KEY},
            )

        route_module._stats_cache["data"] = None
        route_module._stats_cache["expires"] = 0.0

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["indexed_pages"] == 42
        assert second.json()["indexed_pages"] == 42
        assert first_stats_calls == 1
        assert first_queue_calls == 1
        assert mock_stats.call_count == first_stats_calls
        assert mock_queue.call_count == first_queue_calls

    def test_failed_jobs_uses_short_ttl_cache(self, test_client):
        from app.api.routes import indexer as route_module

        route_module._clear_failed_jobs_cache()
        jobs = [
            {
                "job_id": "job-1",
                "url": "https://example.com",
                "last_error": "boom",
                "retry_count": 5,
                "created_at": "2026-03-07T00:00:00Z",
                "updated_at": "2026-03-07T00:01:00Z",
            }
        ]

        with patch(
            "app.api.routes.indexer.index_job_service.get_failed_permanent_jobs"
        ) as mock_jobs:
            mock_jobs.return_value = jobs

            first = test_client.get(
                "/api/v1/indexer/jobs/failed?limit=50",
                headers={"X-API-Key": settings.INDEXER_API_KEY},
            )
            second = test_client.get(
                "/api/v1/indexer/jobs/failed?limit=50",
                headers={"X-API-Key": settings.INDEXER_API_KEY},
            )

        route_module._clear_failed_jobs_cache()

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["jobs"] == jobs
        assert second.json()["jobs"] == jobs
        assert mock_jobs.call_count == 1

    def test_prewarm_stats_cache_populates_cache(self):
        from app.api.routes import indexer as route_module

        route_module._clear_stats_cache()
        route_module._clear_failed_jobs_cache()
        queue_stats = {
            "pending_jobs": 2,
            "processing_jobs": 1,
            "done_jobs": 8,
            "failed_permanent_jobs": 0,
            "total_jobs": 11,
            "oldest_pending_seconds": 4,
        }

        with (
            patch(
                "app.api.routes.indexer.indexer_service.get_index_stats",
                return_value={"total": 24},
            ),
            patch(
                "app.api.routes.indexer.index_job_service.get_queue_stats",
                return_value=queue_stats,
            ),
            patch(
                "app.api.routes.indexer.index_job_service.get_failed_permanent_jobs",
                return_value=[
                    {
                        "job_id": "job-1",
                        "url": "https://example.com",
                        "last_error": "boom",
                        "retry_count": 5,
                        "created_at": "2026-03-07T00:00:00Z",
                        "updated_at": "2026-03-07T00:01:00Z",
                    }
                ],
            ),
        ):
            asyncio.run(route_module.prewarm_stats_cache(delay_seconds=0))

        assert route_module._stats_cache["data"] is not None
        assert route_module._stats_cache["data"]["indexed_pages"] == 24
        assert route_module._failed_jobs_cache[(50, 0)]["data"]["count"] == 1

    def test_maintain_stats_cache_refreshes_periodically(self):
        from app.api.routes import indexer as route_module

        calls = []

        async def fake_prewarm(*, attempts=60, delay_seconds=5.0):
            calls.append((attempts, delay_seconds))
            if len(calls) >= 2:
                raise asyncio.CancelledError

        async def fake_sleep(_):
            return None

        with (
            patch.object(route_module, "prewarm_stats_cache", fake_prewarm),
            patch.object(background_module.asyncio, "sleep", fake_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                asyncio.run(
                    route_module.maintain_stats_cache(refresh_interval_seconds=15)
                )

        assert calls == [(60, 5.0), (1, 0)]

    def test_metrics_endpoint_exposes_queue_metrics(self, test_client):
        enqueue_resp = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={
                "url": "https://metrics.example.com",
                "title": "Metrics",
                "content": "metrics test",
            },
        )
        assert enqueue_resp.status_code == 202

        response = test_client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        body = response.text
        assert "indexer_queue_pending_jobs" in body
        assert "indexer_indexed_pages" in body
