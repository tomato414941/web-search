from unittest.mock import AsyncMock, MagicMock, patch


def test_api_stats(client):
    from frontend.api.routers.stats import _stats_cache

    _stats_cache["data"] = None
    _stats_cache["expires"] = 0

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


def test_api_crawl_empty_url(client):
    # My code returns 400 if url is empty string
    payload = {"url": "   "}
    response = client.post("/api/v1/crawl", json=payload)
    assert response.status_code == 400
    assert response.json() == {"error": "URL is required"}


def test_api_enqueue_empty_url(client):
    payload = {"url": "   "}
    response = client.post("/api/v1/enqueue", json=payload)
    assert response.status_code == 400
    assert response.json() == {"error": "URL is required"}


def test_api_crawl_missing_field(client):
    # Pydantic validation error (422)
    payload = {"other": "value"}
    response = client.post("/api/v1/crawl", json=payload)
    assert response.status_code == 422


def test_api_crawl_alias_returns_deprecation_metadata(client):
    crawler_response = MagicMock()
    crawler_response.status_code = 200
    crawler_response.json.return_value = {"added_count": 1}

    with patch("frontend.api.routers.crawler.httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = crawler_response
        mock_client.return_value.__aenter__.return_value = mock_instance

        response = client.post("/api/v1/crawl", json={"url": "https://example.com"})

    assert response.status_code == 200
    assert response.json()["deprecated"] is True
    assert response.json()["replacement"] == "/api/v1/enqueue"


def test_api_enqueue_proxies_to_crawler_queue(client):
    crawler_response = MagicMock()
    crawler_response.status_code = 200
    crawler_response.json.return_value = {"added_count": 1}

    with patch("frontend.api.routers.crawler.httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = crawler_response
        mock_client.return_value.__aenter__.return_value = mock_instance

        response = client.post("/api/v1/enqueue", json={"url": "https://example.com"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "url": "https://example.com",
        "message": "Queued",
        "added": True,
    }


def test_api_crawl_now_requires_internal_api_key(client):
    response = client.post("/api/v1/crawl-now", json={"url": "https://example.com"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}


def test_api_crawl_now_proxies_to_crawler_service(client):
    crawler_response = MagicMock()
    crawler_response.status_code = 200
    crawler_response.json.return_value = {
        "status": "queued_for_index",
        "url": "https://example.com",
        "message": "Page queued for indexing",
        "job_id": "job-123",
        "outlinks_discovered": 4,
    }

    with (
        patch(
            "frontend.api.routers.crawler.settings.INDEXER_API_KEY", "internal-test-key"
        ),
        patch("frontend.api.routers.crawler.httpx.AsyncClient") as mock_client,
    ):
        mock_instance = AsyncMock()
        mock_instance.post.return_value = crawler_response
        mock_client.return_value.__aenter__.return_value = mock_instance

        response = client.post(
            "/api/v1/crawl-now",
            json={"url": "https://example.com"},
            headers={"X-API-Key": "internal-test-key"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "status": "queued_for_index",
        "url": "https://example.com",
        "message": "Page queued for indexing",
        "job_id": "job-123",
        "outlinks_discovered": 4,
    }
