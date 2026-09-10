import pytest
from web_search_frontend.services.search import search_service, SearchUnavailable


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": -5},
        {"page": "invalid"},
        {"limit": 51},
        {"page": 5, "limit": 50},
        {"q": "a" * 201},
        {"mode": "bm25"},
    ],
)
def test_search_api_rejects_invalid_or_removed_parameters(client, params):
    assert (
        client.get("/search-results", params={"q": "test", **params}).status_code == 422
    )


def test_search_api_accepts_valid_page(client):
    response = client.get(
        "/search-results", params={"q": "test", "page": 2, "limit": 5}
    )
    assert response.status_code == 200
    assert response.json()["page"] == 2
    assert response.json()["per_page"] == 5
    assert response.json()["mode"] == "hybrid"
    assert "requested_mode" not in response.json()


def test_search_failure_is_503_for_api_and_browser(client, monkeypatch):
    def fail(*args, **kwargs):
        raise SearchUnavailable("unavailable")

    monkeypatch.setattr(search_service, "search", fail)
    api = client.get("/search-results?q=test")
    assert api.status_code == 503
    assert "hits" not in api.json()
    page = client.get("/?q=test&lang=ja")
    assert page.status_code == 503
    assert "現在検索を利用できません" in page.text
    assert "結果なし" not in page.text


def test_readiness_requires_hybrid_index(client, monkeypatch):
    from web_search_frontend.api.routers import system

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(system, "_check_opensearch", lambda: {"status": "error"})
    assert client.get("/readyz").status_code == 503
