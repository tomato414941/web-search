"""Tests for public content access."""

from web_search_postgres.search import get_connection

from web_search_frontend.api.routers.search_api import search_service


class TestAPISearchPublicContent:
    def test_search_without_key_succeeds(self):
        from fastapi.testclient import TestClient
        from web_search_frontend.api.main import app

        client = TestClient(app)
        resp = client.get("/search-results", params={"q": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert "usage" not in data

    def test_search_include_content_without_key_returns_content(self, monkeypatch):
        from fastapi.testclient import TestClient
        from web_search_frontend.api.main import app

        def fake_search(
            q: str | None,
            k: int = 10,
            page: int = 1,
            mode: str = "bm25",
            *,
            include_content: bool = False,
        ) -> dict:
            assert include_content is True
            return {
                "query": q,
                "total": 1,
                "page": page,
                "per_page": k,
                "last_page": 1,
                "hits": [
                    {
                        "url": "https://example.com",
                        "title": "Example",
                        "snip": "snippet",
                        "snip_plain": "snippet",
                        "score": 1.0,
                        "content": "full page text",
                    }
                ],
                "mode": mode,
            }

        monkeypatch.setattr(search_service, "search", fake_search)

        client = TestClient(app)
        resp = client.get(
            "/search-results",
            params={"q": "test", "include_content": "true"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "usage" not in data
        assert data["hits"][0]["content"] == "full page text"


class TestAPIContent:
    def test_content_without_key_succeeds(self):
        from fastapi.testclient import TestClient
        from web_search_frontend.api.main import app

        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO documents (url, title, content, word_count)
                VALUES (%s, %s, %s, %s)
                """,
                ("https://example.com", "Example", "full page text", 3),
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()

        client = TestClient(app)
        resp = client.get(
            "/indexed-documents/by-url",
            params={"url": "https://example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "https://example.com"
        assert data["content"] == "full page text"

    def test_content_missing_url_returns_404_without_key(self):
        from fastapi.testclient import TestClient
        from web_search_frontend.api.main import app

        client = TestClient(app)
        resp = client.get(
            "/indexed-documents/by-url",
            params={"url": "https://missing.example.com"},
        )
        assert resp.status_code == 404
