from unittest.mock import patch
from fastapi.testclient import TestClient
from frontend.api.main import app

client = TestClient(app)


def test_health():
    # Mock the httpx.Client used in the health check
    with patch("frontend.api.routers.system.httpx.Client") as MockClient:
        # Configure the mock to return a success response
        mock_instance = MockClient.return_value
        mock_instance.__enter__.return_value.get.return_value.status_code = 200

        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "checks" in data
        assert data["checks"]["crawler"] is True


def test_search_page_loads_default():
    # Helper to check if default load (en) contains "Search"
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # Check for English title logic (assuming fallback is EN)
    assert "Search" in response.text


def test_search_page_lang_en():
    response = client.get("/?lang=en")
    assert response.status_code == 200
    assert "Search" in response.text
    assert "検索" not in response.text


def test_search_page_lang_ja():
    response = client.get("/?lang=ja")
    assert response.status_code == 200
    # "検索" should be present in title or button
    assert "検索" in response.text


def test_search_api_empty_query():
    response = client.get("/api/v1/search")
    assert response.status_code == 200
    data = response.json()
    assert data["hits"] == []
    assert data["total"] == 0


def test_search_api_with_query():
    # Note: This test relies on the DB state.
    # For a unit test, we might want to mock the search service,
    # but for a simple integration test, we can check the structure.
    response = client.get("/api/v1/search?q=test")
    assert response.status_code == 200
    data = response.json()
    assert "hits" in data
    assert "total" in data
    assert "query" in data
    assert data["query"] == "test"
