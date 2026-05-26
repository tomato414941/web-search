"""
API Endpoint Tests

Tests for all FastAPI routes in the crawler service.
"""

import asyncio
from unittest.mock import patch

import pytest

from web_search_core import background as background_module
from web_search_crawler.services.direct_crawl import ImmediateCrawlResult


async def _parked_worker_loop(*args, **kwargs):
    await asyncio.Event().wait()


def test_root_health_endpoint(test_client):
    """Test GET /health endpoint (recommended)"""
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_root_readiness_endpoint(test_client):
    response = test_client.get("/readyz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "checks" in data


def test_crawl_urls_endpoint(test_client, test_url_store):
    """Test POST /api/v1/urls endpoint"""
    with patch(
        "web_search_crawler.api.deps._get_url_store", return_value=test_url_store
    ):
        response = test_client.post(
            "/api/v1/urls",
            json={
                "urls": ["http://example.com", "http://test.com"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "admitted"
        assert data["added_count"] == 2


def test_crawl_now_endpoint(test_client):
    with patch(
        "web_search_crawler.api.routes.crawl.execute_crawl_now",
        return_value=ImmediateCrawlResult(
            status="submitted",
            url="https://example.com",
            message="Page submitted to indexer",
            job_id="job-123",
            outlinks_discovered=3,
        ),
    ):
        response = test_client.post(
            "/api/v1/crawl-now",
            json={"url": "https://example.com"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "submitted",
        "url": "https://example.com/",
        "message": "Page submitted to indexer",
        "job_id": "job-123",
        "outlinks_discovered": 3,
    }


def test_frontier_peek_endpoint(test_client, test_url_store):
    """Test GET /api/v1/frontier endpoint."""
    # Add some URLs to url_store
    test_url_store.discover_and_admit_url("http://example.com")
    test_url_store.discover_and_admit_url("http://test.com")

    with patch(
        "web_search_crawler.api.deps._get_url_store", return_value=test_url_store
    ):
        response = test_client.get("/api/v1/frontier?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["url"] == "http://example.com"


def test_frontier_status_endpoint(test_client, test_url_store):
    """Test GET /api/v1/frontier/status endpoint."""
    from web_search_crawler.api.routes.frontier import _status_cache

    _status_cache["data"] = None
    _status_cache["expires"] = 0

    # Add some data
    test_url_store.discover_and_admit_url("http://example.com")
    test_url_store.record_crawl_result("http://crawled.com", "done")

    with patch(
        "web_search_crawler.api.deps._get_url_store", return_value=test_url_store
    ):
        response = test_client.get("/api/v1/frontier/status")
        assert response.status_code == 200
        data = response.json()
        assert data["pending"] == 1


def test_history_endpoint(test_client):
    """Test GET /api/v1/history endpoint"""
    from web_search_crawler.utils import history

    # Initialize test database
    history.init_db()
    history.log_crawl_attempt("http://test.com", "queued_for_index", 200)

    response = test_client.get("/api/v1/history?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["url"] == "http://test.com"
    assert data[0]["status"] == "queued_for_index"


def test_admin_history_endpoint_returns_operator_read_model(test_client):
    from web_search_crawler.utils import history

    history.init_db()
    history.log_crawl_attempt("http://retry.test", "retry_later", 503, "timeout")

    response = test_client.get("/api/v1/history/admin?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["raw_status"] == "retry_later"
    assert data[0]["status_label"] == "retrying"
    assert data[0]["status_tone"] == "warn"


def test_worker_start_endpoint(test_client, reset_worker_manager):
    """Test POST /api/v1/worker/start endpoint"""
    with patch(
        "web_search_crawler.workers.tasks.worker_loop", side_effect=_parked_worker_loop
    ):
        response = test_client.post("/api/v1/worker/start", json={"concurrency": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert "concurrency=2" in data["message"]


def test_worker_start_exceeds_max_concurrency(test_client, reset_worker_manager):
    """Test POST /api/v1/worker/start with excessive concurrency"""
    response = test_client.post("/api/v1/worker/start", json={"concurrency": 100})
    assert response.status_code == 400
    assert "exceeds maximum" in response.json()["detail"]


def test_worker_start_already_running(test_client, reset_worker_manager):
    """Test POST /api/v1/worker/start when already running"""
    with patch(
        "web_search_crawler.workers.tasks.worker_loop", side_effect=_parked_worker_loop
    ):
        # Start worker
        test_client.post("/api/v1/worker/start", json={"concurrency": 1})

        # Try to start again
        response = test_client.post("/api/v1/worker/start", json={"concurrency": 1})
        assert response.status_code == 400
        assert "already running" in response.json()["detail"]


def test_worker_stop_endpoint(test_client, reset_worker_manager):
    """Test POST /api/v1/worker/stop endpoint"""
    with patch(
        "web_search_crawler.workers.tasks.worker_loop", side_effect=_parked_worker_loop
    ):
        # Start worker first
        test_client.post("/api/v1/worker/start", json={"concurrency": 1})

        # Stop worker
        response = test_client.post("/api/v1/worker/stop", json={"graceful": True})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"


def test_worker_stop_not_running(test_client, reset_worker_manager):
    """Test POST /api/v1/worker/stop when not running"""
    response = test_client.post("/api/v1/worker/stop", json={"graceful": True})
    assert response.status_code == 400
    assert "not running" in response.json()["detail"]


def test_worker_status_stopped(test_client, reset_worker_manager):
    """Test GET /api/v1/worker/status when stopped"""
    response = test_client.get("/api/v1/worker/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stopped"
    assert data["active_tasks"] == 0
    assert data["started_at"] is None
    assert data["concurrency"] is None


def test_worker_status_running(test_client, reset_worker_manager):
    """Test GET /api/v1/worker/status when running"""
    with patch(
        "web_search_crawler.workers.tasks.worker_loop", side_effect=_parked_worker_loop
    ):
        # Start worker
        test_client.post("/api/v1/worker/start", json={"concurrency": 1})

        # Check status
        response = test_client.get("/api/v1/worker/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["started_at"] is not None
        assert data["concurrency"] == 1


def test_seeds_endpoint_supports_pagination(test_client, test_url_store):
    from web_search_crawler.api.routes.seeds import _clear_seeds_cache

    _clear_seeds_cache()
    test_url_store.discover_and_admit_urls(
        [
            "https://example.com/1",
            "https://example.com/2",
            "https://example.com/3",
        ]
    )
    test_url_store.mark_seeds(
        [
            "https://example.com/1",
            "https://example.com/2",
            "https://example.com/3",
        ]
    )

    with patch(
        "web_search_crawler.api.deps._get_url_store", return_value=test_url_store
    ):
        response = test_client.get("/api/v1/seeds?limit=2&offset=0&include_total=true")

    _clear_seeds_cache()

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["items"]) == 2
    assert "status" not in data["items"][0]
    assert "last_crawled_at" not in data["items"][0]


def test_prewarm_seeds_page_cache_populates_first_page(test_url_store):
    from web_search_crawler.api.routes.seeds import (
        _clear_seeds_cache,
        _seeds_cache,
        prewarm_seeds_page_cache,
    )
    from web_search_crawler.services.seeds import SeedService

    _clear_seeds_cache()
    test_url_store.discover_and_admit_urls(
        [
            "https://example.com/1",
            "https://example.com/2",
            "https://example.com/3",
        ]
    )
    test_url_store.mark_seeds(
        [
            "https://example.com/1",
            "https://example.com/2",
            "https://example.com/3",
        ]
    )

    asyncio.run(prewarm_seeds_page_cache(SeedService(test_url_store)))

    payload = _seeds_cache[(50, 0)]["data"]
    assert payload.total == 3
    assert len(payload.items) == 3


def test_maintain_admin_caches_refreshes_periodically():
    from web_search_crawler.core import events

    refresh_calls: list[str] = []
    sleep_calls: list[float] = []

    async def fake_refresh() -> None:
        refresh_calls.append("refresh")
        if len(refresh_calls) >= 2:
            raise asyncio.CancelledError

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)
        return None

    with (
        patch.object(events, "_refresh_admin_caches", fake_refresh),
        patch.object(background_module.asyncio, "sleep", fake_sleep),
    ):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(events.maintain_admin_caches(refresh_interval_seconds=15))

    assert refresh_calls == ["refresh", "refresh"]
    assert sleep_calls == [2, 15]


def test_maintain_frontier_health_reconciles_periodically():
    from web_search_crawler.core import events

    reconcile_calls: list[str] = []
    sleep_calls: list[float] = []

    async def fake_reconcile() -> int:
        reconcile_calls.append("reconcile")
        if len(reconcile_calls) >= 2:
            raise asyncio.CancelledError
        return 1

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)
        return None

    with (
        patch.object(events, "_reconcile_frontier_leases", fake_reconcile),
        patch.object(background_module.asyncio, "sleep", fake_sleep),
    ):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(events.maintain_frontier_health(refresh_interval_seconds=30))

    assert reconcile_calls == ["reconcile", "reconcile"]
    assert sleep_calls == [2, 30]
