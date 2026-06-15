"""Test Indexer API security and synchronous indexing behavior."""

from unittest.mock import AsyncMock, patch

from web_search_indexer.core.config import settings


class TestIndexerAPIAuth:
    """Test indexer API authentication and security."""

    def test_index_page_requires_api_key(self, test_client):
        response = test_client.post(
            "/documents",
            json={
                "url": "https://example.com",
                "title": "Test",
                "content": "Test content",
            },
        )
        assert response.status_code == 422

    def test_index_page_with_invalid_api_key(self, test_client):
        response = test_client.post(
            "/documents",
            headers={"X-API-Key": "wrong-key"},
            json={
                "url": "https://example.com",
                "title": "Test",
                "content": "Test content",
            },
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_index_page_with_valid_api_key(self, test_client):
        response = test_client.post(
            "/documents",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={
                "url": "https://example.com",
                "title": "Test",
                "content": "Test content",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["indexed"] is True
        assert data["url"].rstrip("/") == "https://example.com"

    def test_index_page_with_empty_url(self, test_client):
        response = test_client.post(
            "/documents",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "", "title": "Test", "content": "Test content"},
        )
        assert response.status_code == 422

    def test_index_page_with_invalid_url(self, test_client):
        response = test_client.post(
            "/documents",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "not-a-url", "title": "Test", "content": "Test content"},
        )
        assert response.status_code == 422

    def test_index_page_with_missing_fields(self, test_client):
        response = test_client.post(
            "/documents",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "https://example.com", "content": "Test content"},
        )
        assert response.status_code == 422

        response = test_client.post(
            "/documents",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "https://example.com", "title": "Test"},
        )
        assert response.status_code == 422

    def test_index_page_with_empty_content(self, test_client):
        response = test_client.post(
            "/documents",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "https://example.com", "title": "Test", "content": ""},
        )
        assert response.status_code == 200

    def test_index_page_handles_index_errors_gracefully(self, test_client):
        with patch(
            "web_search_indexer.api.routes.indexer.indexer_service.index_page",
            new_callable=AsyncMock,
        ) as mock_index_page:
            mock_index_page.side_effect = Exception("Database connection failed")

            response = test_client.post(
                "/documents",
                headers={"X-API-Key": settings.INDEXER_API_KEY},
                json={"url": "https://example.com", "title": "Test", "content": "Test"},
            )
            assert response.status_code == 500
            assert "detail" in response.json()

    def test_index_page_with_very_long_content(self, test_client):
        long_content = "x" * 100000
        response = test_client.post(
            "/documents",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={
                "url": "https://example.com",
                "title": "Test",
                "content": long_content,
            },
        )
        assert response.status_code == 200

    def test_index_page_with_special_characters(self, test_client):
        special_content = (
            "Test with émojis 🎉 and 特殊文字 <script>alert('xss')</script>"
        )
        response = test_client.post(
            "/documents",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={
                "url": "https://example.com",
                "title": "Special chars",
                "content": special_content,
            },
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True


class TestIndexerAPIValidation:
    """Test input validation for indexer API."""

    def test_rejects_javascript_protocol(self, test_client):
        response = test_client.post(
            "/documents",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={
                "url": "javascript:alert('xss')",
                "title": "Test",
                "content": "Test",
            },
        )
        assert response.status_code == 422

    def test_accepts_http_and_https_only(self, test_client):
        response = test_client.post(
            "/documents",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "http://example.com", "title": "Test", "content": "Test"},
        )
        assert response.status_code == 200

        response = test_client.post(
            "/documents",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "https://example.com", "title": "Test", "content": "Test"},
        )
        assert response.status_code == 200

    def test_duplicate_url_updates_document(self, test_client):
        url = "https://unique-test.example.com"

        response1 = test_client.post(
            "/documents",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": url, "title": "First Title", "content": "same content"},
        )
        response2 = test_client.post(
            "/documents",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": url, "title": "Different title", "content": "same content"},
        )

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json()["indexed"] is True
        assert response2.json()["indexed"] is True


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_root_health_check(self, test_client):
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_root_readiness_check(self, test_client):
        response = test_client.get("/readyz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "checks" in data

    def test_metrics_endpoint_returns_prometheus_payload(self, test_client):
        response = test_client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
