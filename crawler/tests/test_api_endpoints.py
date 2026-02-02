"""
API Endpoint Tests

Tests for all FastAPI routes in the crawler service.
"""

from unittest.mock import patch


def test_root_health_endpoint(test_client):
    """Test GET /health endpoint (recommended)"""
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_api_v1_health_endpoint(test_client):
    """Test GET /api/v1/health endpoint (backward compatible)"""
    response = test_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_crawl_urls_endpoint(test_client, test_frontier, test_history):
    """Test POST /api/v1/urls endpoint"""
    with patch("app.api.deps._get_frontier", return_value=test_frontier):
        with patch("app.api.deps._get_history", return_value=test_history):
            response = test_client.post(
                "/api/v1/urls",
                json={
                    "urls": ["http://example.com", "http://test.com"],
                    "priority": 100.0,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "queued"
            assert data["added_count"] == 2


def test_queue_peek_endpoint(test_client, test_frontier, test_history):
    """Test GET /api/v1/queue endpoint"""
    # Add some URLs to frontier
    test_frontier.add("http://example.com", priority=100.0)
    test_frontier.add("http://test.com", priority=90.0)

    with patch("app.api.deps._get_frontier", return_value=test_frontier):
        with patch("app.api.deps._get_history", return_value=test_history):
            response = test_client.get("/api/v1/queue?limit=10")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 2
            assert data[0]["url"] == "http://example.com"
            assert data[0]["score"] == 100.0


def test_queue_status_endpoint(test_client, test_frontier, test_history):
    """Test GET /api/v1/status endpoint"""
    # Add some data
    test_frontier.add("http://example.com", priority=100.0)
    test_history.record("http://crawled.com", status="done")

    with patch("app.api.deps._get_frontier", return_value=test_frontier):
        with patch("app.api.deps._get_history", return_value=test_history):
            response = test_client.get("/api/v1/status")
            assert response.status_code == 200
            data = response.json()
            assert data["queue_size"] == 1
            assert data["total_seen"] == 1
            assert data["total_indexed"] == 1
            assert "cache_size" in data  # Backward compat (always 0)


def test_history_endpoint(test_client):
    """Test GET /api/v1/history endpoint"""
    from app.utils import history

    # Initialize test database
    history.init_db()
    history.log_crawl_attempt("http://test.com", "indexed", 200)

    response = test_client.get("/api/v1/history?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["url"] == "http://test.com"
    assert data[0]["status"] == "indexed"


def test_worker_start_endpoint(test_client, reset_worker_manager):
    """Test POST /api/v1/worker/start endpoint"""
    with patch("app.workers.tasks.worker_loop"):
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
    with patch("app.workers.tasks.worker_loop"):
        # Start worker
        test_client.post("/api/v1/worker/start", json={"concurrency": 1})

        # Try to start again
        response = test_client.post("/api/v1/worker/start", json={"concurrency": 1})
        assert response.status_code == 400
        assert "already running" in response.json()["detail"]


def test_worker_stop_endpoint(test_client, reset_worker_manager):
    """Test POST /api/v1/worker/stop endpoint"""
    with patch("app.workers.tasks.worker_loop"):
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


def test_worker_status_running(test_client, reset_worker_manager):
    """Test GET /api/v1/worker/status when running"""
    with patch("app.workers.tasks.worker_loop"):
        # Start worker
        test_client.post("/api/v1/worker/start", json={"concurrency": 1})

        # Check status
        response = test_client.get("/api/v1/worker/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["started_at"] is not None
