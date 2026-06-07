"""
API Endpoint Tests

Tests for all FastAPI routes in the crawler service.
"""

import asyncio
from unittest.mock import patch

import pytest

from web_search_core import background as background_module


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


def test_worker_start_endpoint(test_client, reset_worker_manager):
    """Test POST /worker/start endpoint"""
    with patch(
        "web_search_crawler.workers.tasks.worker_loop", side_effect=_parked_worker_loop
    ):
        response = test_client.post("/worker/start", json={"concurrency": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert "concurrency=2" in data["message"]


def test_worker_start_exceeds_max_concurrency(test_client, reset_worker_manager):
    """Test POST /worker/start with excessive concurrency"""
    response = test_client.post("/worker/start", json={"concurrency": 100})
    assert response.status_code == 400
    assert "exceeds maximum" in response.json()["detail"]


def test_worker_start_already_running(test_client, reset_worker_manager):
    """Test POST /worker/start when already running"""
    with patch(
        "web_search_crawler.workers.tasks.worker_loop", side_effect=_parked_worker_loop
    ):
        # Start worker
        test_client.post("/worker/start", json={"concurrency": 1})

        # Try to start again
        response = test_client.post("/worker/start", json={"concurrency": 1})
        assert response.status_code == 400
        assert "already running" in response.json()["detail"]


def test_worker_stop_endpoint(test_client, reset_worker_manager):
    """Test POST /worker/stop endpoint"""
    with patch(
        "web_search_crawler.workers.tasks.worker_loop", side_effect=_parked_worker_loop
    ):
        # Start worker first
        test_client.post("/worker/start", json={"concurrency": 1})

        # Stop worker
        response = test_client.post("/worker/stop", json={"graceful": True})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"


def test_worker_stop_not_running(test_client, reset_worker_manager):
    """Test POST /worker/stop when not running"""
    response = test_client.post("/worker/stop", json={"graceful": True})
    assert response.status_code == 400
    assert "not running" in response.json()["detail"]


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


def test_frontier_maintenance_uses_runtime_store_factory(monkeypatch):
    from web_search_crawler.core import events
    from web_search_crawler.services import crawl_runtime

    class FakeStore:
        def reconcile_expired_frontier_leases(self):
            return 2

        def reconcile_domain_state_inflight_leases(self):
            return 3

    async def fake_run_in_db_executor(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(
        crawl_runtime, "build_crawler_runtime_store", lambda: FakeStore()
    )
    monkeypatch.setattr(events, "run_in_db_executor", fake_run_in_db_executor)

    assert asyncio.run(events._reconcile_frontier_leases()) == 2
    assert asyncio.run(events._reconcile_domain_state_inflight_leases()) == 3
