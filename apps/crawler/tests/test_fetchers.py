"""Tests for HTTP fetch helpers."""

import pytest

from web_search_crawler.services.fetchers import _read_response_body


class FakeContent:
    def __init__(self, chunks: list[bytes]):
        self.chunks = chunks

    async def iter_chunked(self, _size: int):
        for chunk in self.chunks:
            yield chunk


@pytest.mark.asyncio
async def test_read_response_body_reads_all_chunks():
    body, truncated = await _read_response_body(
        FakeContent([b"<rss><channel>", b"<item>ok</item>", b"</channel></rss>"]),
        max_size=1024,
    )

    assert truncated is False
    assert body == b"<rss><channel><item>ok</item></channel></rss>"


@pytest.mark.asyncio
async def test_read_response_body_reports_truncation_after_limit():
    body, truncated = await _read_response_body(
        FakeContent([b"abc", b"def"]),
        max_size=5,
    )

    assert truncated is True
    assert body == b"abc"
