"""HTTP fetcher implementations for crawler pipelines."""

import time

from dataclasses import dataclass
from typing import Protocol

import aiohttp

from web_search_crawler.core.config import settings

MAX_RESPONSE_SIZE = 10 * 1024 * 1024


@dataclass
class FetchResult:
    """Result of an HTTP fetch."""

    status: int
    content_type: str
    body: str | None = None
    error: str | None = None
    fetch_request_ms: int | None = None
    fetch_body_read_ms: int | None = None


class Fetcher(Protocol):
    async def fetch(self, session: aiohttp.ClientSession, url: str) -> FetchResult: ...


def _is_html_content_type(content_type: str) -> bool:
    return "text/html" in content_type or "application/xhtml" in content_type


def _is_feed_content_type(content_type: str) -> bool:
    return any(
        needle in content_type
        for needle in (
            "application/rss+xml",
            "application/atom+xml",
            "application/xml",
            "text/xml",
        )
    )


class AiohttpFetcher:
    """Default fetcher backed by aiohttp."""

    async def fetch(self, session: aiohttp.ClientSession, url: str) -> FetchResult:
        request_started_at = time.perf_counter()
        async with session.get(
            url,
            timeout=settings.CRAWL_TIMEOUT_SEC,
            allow_redirects=True,
        ) as resp:
            request_ms = max(0, int((time.perf_counter() - request_started_at) * 1000))
            content_type = resp.headers.get("Content-Type", "").lower()

            content_length = resp.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > MAX_RESPONSE_SIZE:
                        return FetchResult(
                            status=resp.status,
                            content_type=content_type,
                            error=f"Response too large: {content_length} bytes",
                            fetch_request_ms=request_ms,
                        )
                except ValueError:
                    pass

            if resp.status != 200 or not (
                _is_html_content_type(content_type)
                or _is_feed_content_type(content_type)
            ):
                return FetchResult(
                    status=resp.status,
                    content_type=content_type,
                    fetch_request_ms=request_ms,
                )

            body_read_started_at = time.perf_counter()
            body = await resp.content.read(MAX_RESPONSE_SIZE)
            body_read_ms = max(
                0, int((time.perf_counter() - body_read_started_at) * 1000)
            )
            if len(body) >= MAX_RESPONSE_SIZE:
                return FetchResult(
                    status=resp.status,
                    content_type=content_type,
                    error=f"Response truncated at {MAX_RESPONSE_SIZE} bytes",
                    fetch_request_ms=request_ms,
                    fetch_body_read_ms=body_read_ms,
                )

            return FetchResult(
                status=resp.status,
                content_type=content_type,
                body=body.decode("utf-8", errors="replace"),
                fetch_request_ms=request_ms,
                fetch_body_read_ms=body_read_ms,
            )
