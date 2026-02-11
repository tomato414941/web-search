from fastapi.testclient import TestClient
from frontend.api.main import app

client = TestClient(app)


def test_health():
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


def test_search_page_loads_default():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Search" in response.text


def test_search_page_lang_en():
    response = client.get("/?lang=en")
    assert response.status_code == 200
    assert "Search" in response.text
    assert "検索" not in response.text


def test_search_page_lang_ja():
    response = client.get("/?lang=ja")
    assert response.status_code == 200
    assert "検索" in response.text


def test_search_api_empty_query():
    response = client.get("/api/v1/search")
    assert response.status_code == 200
    data = response.json()
    assert data["hits"] == []
    assert data["total"] == 0


def test_search_api_with_query():
    response = client.get("/api/v1/search?q=test")
    assert response.status_code == 200
    data = response.json()
    assert "hits" in data
    assert "total" in data
    assert "query" in data
    assert data["query"] == "test"
