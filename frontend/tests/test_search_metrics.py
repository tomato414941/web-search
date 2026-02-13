from fastapi.testclient import TestClient

from frontend.api.main import app
from frontend.core.config import settings
from shared.db.search import get_connection, is_postgres_mode

client = TestClient(app)


def _placeholder() -> str:
    return "%s" if is_postgres_mode() else "?"


def test_search_api_returns_request_id_and_logs_impression():
    response = client.get("/api/v1/search?q=metrics-impression")
    assert response.status_code == 200
    data = response.json()
    assert "request_id" in data
    assert isinstance(data["request_id"], str)
    assert len(data["request_id"]) >= 8

    ph = _placeholder()
    conn = get_connection(settings.DB_PATH)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT event_type, query, request_id
        FROM search_events
        WHERE event_type = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        ("impression",),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    assert row is not None
    assert row[0] == "impression"
    assert row[1] == "metrics-impression"
    assert row[2] == data["request_id"]


def test_search_click_endpoint_logs_click_event():
    search_response = client.get("/api/v1/search?q=metrics-click")
    request_id = search_response.json()["request_id"]

    click_response = client.post(
        "/api/v1/search/click",
        json={
            "request_id": request_id,
            "query": "metrics-click",
            "url": "https://example.com/page",
            "rank": 2,
        },
    )
    assert click_response.status_code == 204

    ph = _placeholder()
    conn = get_connection(settings.DB_PATH)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT event_type, request_id, clicked_rank
        FROM search_events
        WHERE event_type = {ph} AND request_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        ("click", request_id),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    assert row is not None
    assert row[0] == "click"
    assert row[1] == request_id
    assert row[2] == 2


def test_quality_summary_endpoint_returns_metrics():
    ph = _placeholder()
    conn = get_connection(settings.DB_PATH)
    cur = conn.cursor()
    cur.execute(
        f"""
        INSERT INTO search_events (
            event_type, query, query_norm, request_id, result_count, latency_ms
        ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """,
        ("impression", "q1", "q1", "req-a", 0, 120),
    )
    cur.execute(
        f"""
        INSERT INTO search_events (
            event_type, query, query_norm, request_id, result_count, latency_ms
        ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """,
        ("impression", "q2", "q2", "req-b", 3, 240),
    )
    cur.execute(
        f"""
        INSERT INTO search_events (
            event_type, query, query_norm, request_id, clicked_url, clicked_rank
        ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """,
        ("click", "q2", "q2", "req-b", "https://example.com", 3),
    )
    conn.commit()
    cur.close()
    conn.close()

    response = client.get("/api/v1/quality/summary?window=24h")
    assert response.status_code == 200
    data = response.json()

    assert "search" in data
    assert "crawl" in data
    assert data["search"]["impressions"] >= 2
    assert data["search"]["zero_hit_rate"] >= 50.0
    assert data["search"]["click_through_rate"] >= 50.0
    assert data["search"]["avg_click_rank"] >= 3.0


def test_quality_summary_endpoint_rejects_invalid_window():
    response = client.get("/api/v1/quality/summary?window=1h")
    assert response.status_code == 400
