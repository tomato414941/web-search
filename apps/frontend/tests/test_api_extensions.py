from unittest.mock import AsyncMock, MagicMock, patch


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


def test_search_index_returns_indexed_document_total(client):
    with patch(
        "web_search_frontend.api.routers.search_index.get_indexed_document_count",
        return_value=123,
    ):
        response = client.get("/api/v1/search-index")

    assert response.status_code == 200
    assert response.json() == {"documents": {"total": 123}}
