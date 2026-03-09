from frontend.services.search import search_service


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_readyz(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "checks" in data


def test_search_page_loads_default(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Search" in response.text


def test_search_page_lang_en(client):
    response = client.get("/?lang=en")
    assert response.status_code == 200
    assert "Search" in response.text
    assert "検索" not in response.text


def test_search_page_lang_ja(client):
    response = client.get("/?lang=ja")
    assert response.status_code == 200
    assert "検索" in response.text


def test_search_api_empty_query(client):
    response = client.get("/api/v1/search")
    assert response.status_code == 200
    data = response.json()
    assert data["hits"] == []
    assert data["total"] == 0


def test_search_api_with_query(client):
    response = client.get("/api/v1/search?q=test")
    assert response.status_code == 200
    data = response.json()
    assert "hits" in data
    assert "total" in data
    assert "query" in data
    assert data["query"] == "test"


def test_search_page_pagination_links_encode_query_and_preserve_state(
    client, monkeypatch
):
    def fake_search(
        q: str | None,
        k: int = 10,
        page: int = 1,
        mode: str = "auto",
        *,
        include_content: bool = False,
    ) -> dict:
        return {
            "query": q,
            "total": 25,
            "page": page,
            "per_page": k,
            "last_page": 3,
            "hits": [
                {
                    "url": "https://example.com",
                    "title": "Example",
                    "snip": "snippet",
                    "snip_plain": "snippet",
                    "rank": 1.0,
                }
            ],
            "mode": mode,
        }

    monkeypatch.setattr(search_service, "search", fake_search)

    response = client.get(
        "/",
        params={
            "q": "C++ & Rust",
            "page": "2",
            "mode": "modern",
            "lang": "ja",
        },
    )

    assert response.status_code == 200
    assert (
        'href="/?q=C%2B%2B+%26+Rust&amp;page=1&amp;mode=modern&amp;lang=ja"'
    ) in response.text
    assert (
        'href="/?q=C%2B%2B+%26+Rust&amp;page=3&amp;mode=modern&amp;lang=ja"'
    ) in response.text


def test_search_page_form_preserves_lang(client, monkeypatch):
    def fake_search(
        q: str | None,
        k: int = 10,
        page: int = 1,
        mode: str = "auto",
        *,
        include_content: bool = False,
    ) -> dict:
        return {
            "query": q,
            "total": 25,
            "page": page,
            "per_page": k,
            "last_page": 3,
            "hits": [
                {
                    "url": "https://example.com",
                    "title": "Example",
                    "snip": "snippet",
                    "snip_plain": "snippet",
                    "rank": 1.0,
                }
            ],
            "mode": mode,
        }

    monkeypatch.setattr(search_service, "search", fake_search)

    response = client.get(
        "/",
        params={
            "q": "test",
            "mode": "simple",
            "lang": "ja",
        },
    )

    assert response.status_code == 200
    assert '<input type="hidden" name="mode" value="simple">' in response.text
    assert '<input type="hidden" name="lang" value="ja">' in response.text
