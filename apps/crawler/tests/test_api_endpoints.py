"""
API Endpoint Tests

Tests for all FastAPI routes in the crawler service.
"""


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


def test_worker_control_endpoints_are_not_exposed(test_client):
    assert test_client.post("/worker/start", json={"concurrency": 1}).status_code == 404
    assert test_client.post("/worker/stop", json={"graceful": True}).status_code == 404
