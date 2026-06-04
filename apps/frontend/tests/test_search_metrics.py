from web_search_postgres.search import get_connection


def test_search_api_records_request_and_impressions(client):
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
    assert impression_count == len(data["hits"])
    if data["hits"]:
        assert data["hits"][0]["impression_id"]


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
