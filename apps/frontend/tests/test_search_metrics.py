import pytest

from web_search_frontend.services.search import search_service
from web_search_postgres.search import get_connection


@pytest.fixture
def search_hit(monkeypatch):
    def search(query, limit=10, page=1, mode="bm25", *, include_content=False):
        return {
            "query": query,
            "total": 1,
            "page": page,
            "per_page": limit,
            "last_page": 1,
            "mode": mode,
            "hits": [
                {
                    "url": "https://example.com/",
                    "title": "Example",
                    "snip": "Example snippet",
                    "snip_plain": "Example snippet",
                    "score": 1.0,
                }
            ],
        }

    monkeypatch.setattr(search_service, "search", search)


def test_search_api_records_request_without_browser_tracking(client, search_hit):
    response = client.get("/search-results?q=metrics-impression")
    assert response.status_code == 200
    data = response.json()
    assert "request_id" in data
    assert isinstance(data["request_id"], str)
    assert len(data["request_id"]) >= 8

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT query, source, result_count
        FROM search_requests
        WHERE id = %s
        """,
        (data["request_id"],),
    )
    request_row = cur.fetchone()
    cur.execute(
        """
        SELECT COUNT(*)
        FROM search_result_impressions
        WHERE search_request_id = %s
        """,
        (data["request_id"],),
    )
    impression_count = cur.fetchone()[0]
    cur.close()
    conn.close()

    assert request_row is not None
    assert request_row[0] == "metrics-impression"
    assert request_row[1] == "public_api"
    assert request_row[2] == data["total"]
    assert impression_count == 0
    assert "impression_id" not in data["hits"][0]
    assert "anon_sid" not in response.cookies


def test_search_ui_records_visible_impressions_and_clicks(client, search_hit):
    response = client.get("/?q=browser-impression")
    assert response.status_code == 200
    assert "anon_sid" in response.cookies

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT i.id FROM search_result_impressions i "
            "JOIN search_requests r ON r.id = i.search_request_id "
            "WHERE r.query = %s AND r.source = 'web_ui'",
            ("browser-impression",),
        )
        rows = cur.fetchall()
    conn.close()
    assert len(rows) == 1
    impression_id = rows[0][0]
    assert f'data-impression-id="{impression_id}"' in response.text
    assert (
        client.post(
            "/events/search-result-clicked", json={"impression_id": impression_id}
        ).status_code
        == 204
    )


def test_search_click_endpoint_logs_click_event(client):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO search_requests (
            id, query, query_norm, source, mode, page, result_limit, result_count
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        ("req-click", "metrics-click", "metrics-click", "public_api", "bm25", 1, 10, 1),
    )
    cur.execute(
        """
        INSERT INTO search_result_impressions (
            id, search_request_id, rank, url, title, score
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        ("imp-click", "req-click", 1, "https://example.com", "Example", 1.0),
    )
    conn.commit()
    cur.close()
    conn.close()

    click_response = client.post(
        "/events/search-result-clicked",
        json={"impression_id": "imp-click"},
    )
    assert click_response.status_code == 204

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.impression_id, i.rank
        FROM search_result_clicks c
        JOIN search_result_impressions i ON i.id = c.impression_id
        WHERE c.impression_id = %s
        """,
        ("imp-click",),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    assert row is not None
    assert row[0] == "imp-click"
    assert row[1] == 1


def test_search_click_endpoint_rejects_unknown_impression(client):
    response = client.post(
        "/events/search-result-clicked",
        json={"impression_id": "missing-impression"},
    )
    assert response.status_code == 404
