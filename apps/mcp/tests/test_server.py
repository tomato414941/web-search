from unittest.mock import AsyncMock, patch

import pytest

from paleblue_mcp.server import _format_hits, fetch_content, web_search

MOCK_SEARCH_DATA = {
    "query": "python frameworks",
    "total": 2,
    "page": 1,
    "per_page": 10,
    "last_page": 1,
    "mode": "bm25",
    "hits": [
        {
            "url": "https://fastapi.tiangolo.com",
            "title": "FastAPI",
            "snip_plain": "Modern Python web framework",
            "rank": 15.0,
            "indexed_at": "2026-03-01T00:00:00+00:00",
        },
        {
            "url": "https://flask.palletsprojects.com",
            "title": "Flask",
            "snip_plain": "Lightweight WSGI framework",
            "rank": 12.0,
            "indexed_at": "2026-02-28T00:00:00+00:00",
        },
    ],
}


def test_format_hits_markdown():
    result = _format_hits(MOCK_SEARCH_DATA)
    assert "## Search: python frameworks" in result
    assert "**2 results**" in result
    assert "[FastAPI](https://fastapi.tiangolo.com)" in result
    assert "Modern Python web framework" in result
    assert "Indexed: 2026-03-01" in result


def test_format_hits_empty():
    data = {
        "query": "nothing",
        "total": 0,
        "page": 1,
        "last_page": 1,
        "mode": "bm25",
        "hits": [],
    }
    result = _format_hits(data)
    assert "No results found" in result


def test_format_hits_untitled():
    data = {
        "query": "test",
        "total": 1,
        "page": 1,
        "last_page": 1,
        "mode": "bm25",
        "hits": [
            {
                "url": "https://example.com",
                "title": None,
                "snip_plain": "Some text",
                "rank": 5.0,
                "indexed_at": None,
            }
        ],
    }
    result = _format_hits(data)
    assert "[Untitled](https://example.com)" in result


@pytest.mark.asyncio
async def test_web_search_clamps_limit():
    with patch("paleblue_mcp.server._client") as mock_client:
        mock_client.search = AsyncMock(return_value=MOCK_SEARCH_DATA)
        await web_search("test", limit=100)
        assert mock_client.search.call_args.kwargs["limit"] == 50


@pytest.mark.asyncio
async def test_web_search_clamps_negative_limit():
    with patch("paleblue_mcp.server._client") as mock_client:
        mock_client.search = AsyncMock(return_value=MOCK_SEARCH_DATA)
        await web_search("test", limit=-5)
        assert mock_client.search.call_args.kwargs["limit"] == 1


@pytest.mark.asyncio
async def test_web_search_error_handling():
    with patch("paleblue_mcp.server._client") as mock_client:
        mock_client.search = AsyncMock(side_effect=Exception("Network error"))
        result = await web_search("test")
        assert "Search failed" in result
        assert "Network error" in result


@pytest.mark.asyncio
async def test_fetch_content_error():
    with patch("paleblue_mcp.server._client") as mock_client:
        mock_client.get_content = AsyncMock(side_effect=Exception("Not found"))
        result = await fetch_content("https://missing.com")
        assert "Content fetch failed" in result
