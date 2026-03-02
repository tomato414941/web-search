from unittest.mock import AsyncMock, patch

import httpx
import pytest

from paleblue_mcp.client import PaleBlueClient

MOCK_SEARCH_RESPONSE = {
    "query": "python",
    "total": 1,
    "page": 1,
    "per_page": 10,
    "last_page": 1,
    "hits": [
        {
            "url": "https://python.org",
            "title": "Python",
            "snip": "<mark>Python</mark> programming",
            "snip_plain": "Python programming",
            "rank": 10.5,
            "indexed_at": "2026-03-01T00:00:00+00:00",
            "published_at": None,
        }
    ],
    "mode": "bm25",
    "requested_mode": "auto",
    "request_id": "abc123",
}

MOCK_STATS_RESPONSE = {
    "queue": {"queued": 100, "visited": 5000},
    "index": {"indexed": 4500},
}


@pytest.mark.asyncio
async def test_search_sends_correct_params():
    client = PaleBlueClient(base_url="https://example.com", api_key="pbs_test")
    mock_resp = httpx.Response(
        200,
        json=MOCK_SEARCH_RESPONSE,
        request=httpx.Request("GET", "https://example.com"),
    )

    with patch(
        "httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp
    ) as mock_get:
        await client.search("python", limit=5, mode="hybrid")
        call_kwargs = mock_get.call_args
        assert call_kwargs.kwargs["params"]["q"] == "python"
        assert call_kwargs.kwargs["params"]["limit"] == 5
        assert call_kwargs.kwargs["params"]["mode"] == "hybrid"
        assert call_kwargs.kwargs["headers"]["X-API-Key"] == "pbs_test"


@pytest.mark.asyncio
async def test_search_returns_json():
    client = PaleBlueClient(base_url="https://example.com")
    mock_resp = httpx.Response(
        200,
        json=MOCK_SEARCH_RESPONSE,
        request=httpx.Request("GET", "https://example.com"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        result = await client.search("python")
        assert result["total"] == 1
        assert len(result["hits"]) == 1
        assert result["hits"][0]["url"] == "https://python.org"


@pytest.mark.asyncio
async def test_search_no_api_key():
    client = PaleBlueClient(base_url="https://example.com", api_key="")
    mock_resp = httpx.Response(
        200,
        json=MOCK_SEARCH_RESPONSE,
        request=httpx.Request("GET", "https://example.com"),
    )

    with patch(
        "httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp
    ) as mock_get:
        await client.search("python")
        assert "X-API-Key" not in mock_get.call_args.kwargs["headers"]


@pytest.mark.asyncio
async def test_get_stats():
    client = PaleBlueClient(base_url="https://example.com")
    mock_resp = httpx.Response(
        200,
        json=MOCK_STATS_RESPONSE,
        request=httpx.Request("GET", "https://example.com"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        result = await client.get_stats()
        assert result["index"]["indexed"] == 4500
        assert result["queue"]["queued"] == 100


@pytest.mark.asyncio
async def test_search_raises_on_http_error():
    client = PaleBlueClient(base_url="https://example.com")
    mock_resp = httpx.Response(
        429, text="Rate limited", request=httpx.Request("GET", "https://example.com")
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(httpx.HTTPStatusError):
            await client.search("python")
