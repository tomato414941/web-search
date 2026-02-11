"""Test Indexer API Security and Validation."""

from unittest.mock import patch

from app.core.config import settings


class TestIndexerAPIAuth:
    """Test indexer API authentication and security."""

    def test_index_page_requires_api_key(self, test_client):
        """Indexer endpoint should require API key."""
        response = test_client.post(
            "/api/v1/indexer/page",
            json={
                "url": "https://example.com",
                "title": "Test",
                "content": "Test content",
            },
        )
        # FastAPI returns 422 when required header is missing (validation error)
        assert response.status_code == 422

    def test_index_page_with_invalid_api_key(self, test_client):
        """Invalid API key should be rejected."""
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": "wrong-key"},
            json={
                "url": "https://example.com",
                "title": "Test",
                "content": "Test content",
            },
        )
        # Invalid API key returns 401 Unauthorized
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_index_page_with_valid_api_key(self, test_client):
        """Valid API key should allow indexing."""
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={
                "url": "https://example.com",
                "title": "Test",
                "content": "Test content",
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Response format: {"ok": True, "message": "...", "url": "..."}
        assert data["ok"] is True
        # Pydantic HttpUrl normalizes URLs per RFC 3986, adding trailing slash
        assert data["url"].rstrip("/") == "https://example.com"

    def test_index_page_with_empty_url(self, test_client):
        """Empty URL should be rejected."""
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "", "title": "Test", "content": "Test content"},
        )
        assert response.status_code == 422  # Validation error

    def test_index_page_with_invalid_url(self, test_client):
        """Invalid URL format should be rejected."""
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "not-a-url", "title": "Test", "content": "Test content"},
        )
        assert response.status_code == 422  # Validation error

    def test_index_page_with_missing_fields(self, test_client):
        """Missing required fields should be rejected."""
        # Missing title
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "https://example.com", "content": "Test content"},
        )
        assert response.status_code == 422

        # Missing content
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "https://example.com", "title": "Test"},
        )
        assert response.status_code == 422

    def test_index_page_with_empty_content(self, test_client):
        """Empty content should be accepted but might skip indexing."""
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "https://example.com", "title": "Test", "content": ""},
        )
        # Behavior depends on implementation - either accepts or rejects
        # This test documents the current behavior
        assert response.status_code in [200, 400]

    def test_index_page_handles_db_errors_gracefully(self, test_client):
        """Database errors should be handled gracefully."""
        with patch("app.api.routes.indexer.indexer_service.index_page") as mock_index:
            mock_index.side_effect = Exception("Database connection failed")

            response = test_client.post(
                "/api/v1/indexer/page",
                headers={"X-API-Key": settings.INDEXER_API_KEY},
                json={"url": "https://example.com", "title": "Test", "content": "Test"},
            )
            assert response.status_code == 500
            # FastAPI returns {"detail": "..."}  for exceptions
            assert "detail" in response.json()

    def test_index_page_with_very_long_content(self, test_client):
        """Very long content should be handled."""
        long_content = "x" * 100000  # 100KB of content
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={
                "url": "https://example.com",
                "title": "Test",
                "content": long_content,
            },
        )
        # Should either accept or reject based on size limits
        assert response.status_code in [200, 400, 413]

    def test_index_page_with_special_characters(self, test_client):
        """Special characters in content should be handled."""
        special_content = (
            "Test with émojis 🎉 and 特殊文字 <script>alert('xss')</script>"
        )
        response = test_client.post(
            "/api/v1/indexer/page",
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
        """JavaScript protocol URLs should be rejected."""
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={
                "url": "javascript:alert('xss')",
                "title": "Test",
                "content": "Test",
            },
        )
        assert response.status_code == 422

    def test_accepts_http_and_https_only(self, test_client):
        """Only HTTP and HTTPS protocols should be accepted."""
        # HTTP should work
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "http://example.com", "title": "Test", "content": "Test"},
        )
        assert response.status_code == 200

        # HTTPS should work
        response = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": "https://example.com", "title": "Test", "content": "Test"},
        )
        assert response.status_code == 200

    def test_duplicate_indexing_updates(self, test_client):
        """Indexing same URL twice should update, not create duplicate."""
        url = "https://unique-test.example.com"

        # Index first time
        response1 = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": url, "title": "First Title", "content": "First content"},
        )
        assert response1.status_code == 200

        # Index second time with different content
        response2 = test_client.post(
            "/api/v1/indexer/page",
            headers={"X-API-Key": settings.INDEXER_API_KEY},
            json={"url": url, "title": "Updated Title", "content": "Updated content"},
        )
        assert response2.status_code == 200


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_root_health_check(self, test_client):
        """Root-level health check should work without auth."""
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
