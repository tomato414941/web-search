from fastapi.testclient import TestClient
from frontend.api.main import app
from frontend.core.config import settings

MAX_QUERY_LEN = settings.MAX_QUERY_LEN
MAX_PER_PAGE = settings.MAX_PER_PAGE
MAX_PAGE = settings.MAX_PAGE

client = TestClient(app)


def test_search_api_pagination_params():
    # Valid page - with no results, page is clamped to last_page (1)
    response = client.get("/api/v1/search?q=test&page=2")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] >= 1

    # Invalid page (0 or negative) -> should default to 1
    response = client.get("/api/v1/search?q=test&page=0")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1

    response = client.get("/api/v1/search?q=test&page=-5")
    assert response.status_code == 200
    assert response.json()["page"] == 1


def test_search_api_page_limit():
    # Requesting a page beyond MAX_PAGE - with no results, page is clamped to last_page
    response = client.get(f"/api/v1/search?q=test&page={MAX_PAGE + 10}")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] >= 1


def test_search_api_invalid_page_type():
    # Non-integer page -> should default to 1
    response = client.get("/api/v1/search?q=test&page=invalid")
    assert response.status_code == 200
    assert response.json()["page"] == 1


def test_search_api_limit_param():
    # Valid limit
    response = client.get("/api/v1/search?q=test&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert data["per_page"] == 5

    # Exceeding MAX_PER_PAGE
    response = client.get(f"/api/v1/search?q=test&limit={MAX_PER_PAGE + 100}")
    assert response.status_code == 200
    assert response.json()["per_page"] == MAX_PER_PAGE


def test_search_api_query_length_truncation():
    # Construct a query longer than MAX_QUERY_LEN
    long_query = "a" * (MAX_QUERY_LEN + 50)
    response = client.get(f"/api/v1/search?q={long_query}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["query"]) == MAX_QUERY_LEN
    assert data["query"] == long_query[:MAX_QUERY_LEN]


def test_search_special_characters():
    # Just ensure it doesn't crash 500
    response = client.get("/api/v1/search?q=%22%27%3Cscript%3E")
    assert response.status_code == 200
