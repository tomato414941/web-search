def test_api_stats(client):
    from frontend.api.routers.stats import _stats_cache

    _stats_cache["data"] = None
    _stats_cache["expires"] = 0

    response = client.get("/api/v1/stats")
    assert response.status_code == 200
    data = response.json()
    assert "queue" in data
    assert "index" in data
    assert "queued" in data["queue"]
    assert "visited" in data["queue"]
    assert "indexed" in data["index"]
    # Values should be integers
    assert isinstance(data["queue"]["queued"], int)
    assert isinstance(data["index"]["indexed"], int)


def test_api_crawl_empty_url(client):
    # My code returns 400 if url is empty string
    payload = {"url": "   "}
    response = client.post("/api/v1/crawl", json=payload)
    assert response.status_code == 400
    assert response.json() == {"error": "URL is required"}


def test_api_crawl_missing_field(client):
    # Pydantic validation error (422)
    payload = {"other": "value"}
    response = client.post("/api/v1/crawl", json=payload)
    assert response.status_code == 422
