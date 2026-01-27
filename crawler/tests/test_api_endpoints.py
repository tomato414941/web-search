"""
API Endpoint Tests

Tests for all FastAPI routes in the crawler service.
"""

from unittest.mock import patch, MagicMock


def test_health_endpoint(test_client):
    """Test GET /api/v1/health endpoint"""
    response = test_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_crawl_urls_endpoint(test_client, mock_redis):
    """Test POST /api/v1/urls endpoint"""
    # Mock enqueue_batch at the point where QueueService calls it
    with patch("app.api.deps.get_redis", return_value=mock_redis):
        with patch("app.services.queue.enqueue_batch", return_value=2):
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


def test_queue_peek_endpoint(test_client, mock_redis):
    """Test GET /api/v1/queue endpoint"""
    mock_redis.zrange.return_value = [
        (b"http://example.com", 100.0),
        (b"http://test.com", 90.0),
    ]

    with patch("app.api.deps.get_redis", return_value=mock_redis):
        response = test_client.get("/api/v1/queue?limit=10")
        assert response.status_code == 200
        data = response.json()
        # Response is a list[QueueItem], not a dict
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["url"] == "http://example.com"
        assert data[0]["score"] == 100.0


def test_queue_status_endpoint(test_client, mock_redis):
    """Test GET /api/v1/status endpoint"""
    mock_redis.zcard.return_value = 50
    mock_redis.scard.return_value = 1000

    # Mock HybridSeenStore
    mock_seen_store = MagicMock()
    mock_seen_store.get_stats.return_value = {
        "total_seen": 5000,
        "active_seen": 1000,
        "cache_size": 500,
    }

    # Reset global _seen_store and mock _get_seen_store
    import app.services.queue as queue_module

    original_seen_store = queue_module._seen_store
    queue_module._seen_store = None

    try:
        with patch("app.api.deps.get_redis", return_value=mock_redis):
            with patch.object(
                queue_module, "_get_seen_store", return_value=mock_seen_store
            ):
                response = test_client.get("/api/v1/status")
                assert response.status_code == 200
                data = response.json()
                # New domain model with HybridSeenStore stats
                assert data["queue_size"] == 50
                assert data["total_seen"] == 5000
                assert data["active_seen"] == 1000
                assert data["cache_size"] == 500
                # total_crawled is now alias for active_seen (backward compat)
                assert data["total_crawled"] == 1000
                assert "total_indexed" in data
    finally:
        queue_module._seen_store = original_seen_store


def test_history_endpoint(test_client):
    """Test GET /api/v1/history endpoint"""
    from app.utils import history

    # Initialize test database
    history.init_db()
    history.log_crawl_attempt("http://test.com", "indexed", 200)

    response = test_client.get("/api/v1/history?limit=10")
    assert response.status_code == 200
    data = response.json()
    # Response is a list[dict], not a dict with "history" key
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
