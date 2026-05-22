from unittest.mock import AsyncMock, MagicMock, patch


def test_api_stats(client):
    from web_search_frontend.api.routers.stats import _stats_cache

    _stats_cache["data"] = None
    _stats_cache["expires"] = 0

    response = client.get("/api/v1/stats")
    assert response.status_code == 200
    data = response.json()
    assert "frontier" in data
    assert "index" in data
    assert "pending" in data["frontier"]
    assert "indexed" in data["index"]
    # Values should be integers
    assert isinstance(data["frontier"]["pending"], int)
    assert isinstance(data["index"]["indexed"], int)


def test_api_stats_uses_last_successful_crawler_snapshot_on_timeout(client):
    from web_search_frontend.api.routers.stats import _crawler_stats_cache, _stats_cache
    import httpx

    _stats_cache["data"] = None
    _stats_cache["expires"] = 0
    _crawler_stats_cache["data"] = {"pending": 12}
    _crawler_stats_cache["expires"] = float("inf")

    with (
        patch("web_search_frontend.api.routers.stats.httpx.AsyncClient") as mock_client,
        patch(
            "web_search_frontend.api.routers.stats.search_service.get_index_stats",
            return_value={"indexed": 56},
        ),
    ):
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = httpx.ReadTimeout("crawler timed out")
        mock_client.return_value.__aenter__.return_value = mock_instance

        response = client.get("/api/v1/stats")

    _stats_cache["data"] = None
    _stats_cache["expires"] = 0
    _crawler_stats_cache["data"] = None
    _crawler_stats_cache["expires"] = 0

    assert response.status_code == 200
    assert response.json() == {
        "frontier": {"pending": 12},
        "index": {"indexed": 56},
    }


def test_api_urls_empty_url(client):
    payload = {"url": "   "}
    response = client.post("/api/v1/urls", json=payload)
    assert response.status_code == 400
    assert response.json() == {"error": "URL is required"}


def test_api_urls_missing_field(client):
    # Pydantic validation error (422)
    payload = {"other": "value"}
    response = client.post("/api/v1/urls", json=payload)
    assert response.status_code == 422


def test_api_urls_proxies_to_crawler_frontier(client):
    crawler_response = MagicMock()
    crawler_response.status_code = 200
    crawler_response.json.return_value = {"added_count": 1}

    with patch(
        "web_search_frontend.api.routers.crawler.httpx.AsyncClient"
    ) as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = crawler_response
        mock_client.return_value.__aenter__.return_value = mock_instance

        response = client.post("/api/v1/urls", json={"url": "https://example.com"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "url": "https://example.com",
        "message": "Admitted",
        "added": True,
    }


def test_removed_public_aliases_return_404(client):
    crawl_response = client.post("/api/v1/crawl", json={"url": "https://example.com"})
    removed_submit_alias = client.post(
        "/api/v1/enqueue", json={"url": "https://example.com"}
    )

    assert crawl_response.status_code == 404
    assert removed_submit_alias.status_code == 404


def test_api_crawl_now_requires_internal_api_key(client):
    response = client.post("/api/v1/crawl-now", json={"url": "https://example.com"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}


def test_api_crawl_now_proxies_to_crawler_service(client):
    crawler_response = MagicMock()
    crawler_response.status_code = 200
    crawler_response.json.return_value = {
        "status": "submitted",
        "url": "https://example.com",
        "message": "Page submitted to indexer",
        "job_id": "job-123",
        "outlinks_discovered": 4,
    }

    with (
        patch(
            "web_search_frontend.api.routers.crawler.settings.INDEXER_API_KEY",
            "internal-test-key",
        ),
        patch(
            "web_search_frontend.api.routers.crawler.httpx.AsyncClient"
        ) as mock_client,
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
        "status": "submitted",
        "url": "https://example.com",
        "message": "Page submitted to indexer",
        "job_id": "job-123",
        "outlinks_discovered": 4,
    }
