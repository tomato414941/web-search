from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from frontend.api.main import app

client = TestClient(app)


def test_api_stats():
    response = client.get("/api/v1/stats")
    assert response.status_code == 200
    data = response.json()
    assert "queue" in data
    assert "index" in data
    assert "queued" in data["queue"]
    assert "visited" in data["queue"]
    assert "indexed" in data["index"]
    # Values should be integers
    assert isinstance(data["queue"]["queued"], int)
    assert isinstance(data["index"]["indexed"], int)


def test_api_crawl_success():
    # Attempt to queue a valid URL
    # We use a unique URL to hopefully trigger "Queued" logic,
    # but even if "Already seen", it returns 200.
    # Mock the httpx.AsyncClient to simulate successful Crawler response
    from unittest.mock import MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "queued", "added_count": 1, "added": 1}

    with patch("frontend.api.routers.crawler.httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_instance

        payload = {"url": "http://test-api.local/new-page"}
        response = client.post("/api/v1/crawl", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["url"] == "http://test-api.local/new-page"
        assert "message" in data


def test_api_crawl_empty_url():
    # My code returns 400 if url is empty string
    payload = {"url": "   "}
    response = client.post("/api/v1/crawl", json=payload)
    assert response.status_code == 400
    assert response.json() == {"error": "URL is required"}


def test_api_crawl_missing_field():
    # Pydantic validation error (422)
    payload = {"other": "value"}
    response = client.post("/api/v1/crawl", json=payload)
    assert response.status_code == 422
