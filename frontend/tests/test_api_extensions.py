from unittest.mock import AsyncMock, MagicMock, patch
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
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "queued", "added_count": 1}

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
        assert data["added"] is True
        assert data["message"] == "Queued"


def test_api_stats_maps_crawler_contract_fields():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"queue_size": 7, "active_seen": 19}

    with (
        patch("frontend.api.routers.stats.httpx.AsyncClient") as mock_client,
        patch("frontend.api.routers.stats.search_service.get_index_stats") as mock_db,
    ):
        mock_instance = AsyncMock()
        mock_instance.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_instance
        mock_db.return_value = {"indexed": 42}

        response = client.get("/api/v1/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["queue"]["queued"] == 7
    assert data["queue"]["visited"] == 19
    assert data["index"]["indexed"] == 42


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
