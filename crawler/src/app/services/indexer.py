"""
Indexer Service

Submits crawled pages to the Indexer API.
Includes circuit breaker to skip submissions during prolonged indexer outages.
"""

import json
import logging
import os
import time
from dataclasses import dataclass
import aiohttp

logger = logging.getLogger(__name__)

MAX_ERROR_DETAIL_LENGTH = 240

INDEXER_TIMEOUT_SEC = int(os.getenv("INDEXER_SUBMIT_TIMEOUT_SEC", "10"))
CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5"))
CIRCUIT_BREAKER_RESET_SEC = int(os.getenv("CIRCUIT_BREAKER_RESET_SEC", "60"))


@dataclass(frozen=True)
class IndexerSubmitResult:
    ok: bool
    status_code: int | None = None
    detail: str | None = None
    job_id: str | None = None


class _CircuitBreaker:
    """Simple circuit breaker for indexer API calls."""

    def __init__(self, threshold: int, reset_seconds: int):
        self._threshold = threshold
        self._reset_seconds = reset_seconds
        self._consecutive_failures = 0
        self._open_until: float = 0.0

    def is_open(self) -> bool:
        if self._consecutive_failures < self._threshold:
            return False
        return time.monotonic() < self._open_until

    def record_success(self) -> None:
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._threshold:
            self._open_until = time.monotonic() + self._reset_seconds
            logger.warning(
                "Circuit breaker OPEN: %d consecutive failures, "
                "skipping indexer for %ds",
                self._consecutive_failures,
                self._reset_seconds,
            )


_circuit_breaker = _CircuitBreaker(CIRCUIT_BREAKER_THRESHOLD, CIRCUIT_BREAKER_RESET_SEC)


def _normalize_error_text(text: str) -> str:
    normalized = " ".join(text.split())
    if len(normalized) > MAX_ERROR_DETAIL_LENGTH:
        return normalized[: MAX_ERROR_DETAIL_LENGTH - 3] + "..."
    return normalized


def _describe_exception(exc: Exception) -> str:
    detail = str(exc).strip()
    if detail:
        return f"{exc.__class__.__name__}: {detail}"
    return exc.__class__.__name__


def _summarize_indexer_error(status_code: int, body: str) -> str:
    body = (body or "").strip()
    if not body:
        return f"Indexer {status_code}"

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return f"Indexer {status_code}: {_normalize_error_text(body)}"

    detail = parsed.get("detail")
    if isinstance(detail, str):
        return f"Indexer {status_code}: {_normalize_error_text(detail)}"
    if isinstance(detail, list) and detail:
        first = detail[0]
        if isinstance(first, dict):
            candidate = first.get("type") or first.get("msg") or str(first)
            return f"Indexer {status_code}: {_normalize_error_text(str(candidate))}"
        return f"Indexer {status_code}: {_normalize_error_text(str(first))}"

    return f"Indexer {status_code}: {_normalize_error_text(body)}"


async def submit_page_to_indexer(
    session: aiohttp.ClientSession,
    api_url: str,
    api_key: str,
    url: str,
    title: str,
    content: str,
    outlinks: list[str] | None = None,
    published_at: str | None = None,
    updated_at: str | None = None,
    author: str | None = None,
    organization: str | None = None,
) -> IndexerSubmitResult:
    """
    Submit a page to the Indexer API

    Args:
        session: aiohttp client session
        api_url: Full URL to indexer endpoint
        api_key: API key for authentication
        url: Page URL
        title: Page title
        content: Page content
        outlinks: List of discovered outbound URLs

    Returns:
        IndexerSubmitResult containing success, status code, and error details.
    """
    if _circuit_breaker.is_open():
        return IndexerSubmitResult(
            ok=False, detail="Circuit breaker open, indexer skipped"
        )

    try:
        headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "url": url,
            "title": title,
            "content": content,
        }
        if outlinks:
            payload["outlinks"] = outlinks
        if published_at:
            payload["published_at"] = published_at
        if updated_at:
            payload["updated_at"] = updated_at
        if author:
            payload["author"] = author
        if organization:
            payload["organization"] = organization

        async with session.post(
            api_url, json=payload, headers=headers, timeout=INDEXER_TIMEOUT_SEC
        ) as resp:
            if resp.status == 202:
                response_body = await resp.json()
                job_id = response_body.get("job_id")
                logger.info(f"✅ Queued for indexing: {url} (job_id={job_id})")
                _circuit_breaker.record_success()
                return IndexerSubmitResult(
                    ok=True,
                    status_code=resp.status,
                    job_id=str(job_id) if job_id else None,
                )

            error_text = await resp.text()
            detail = _summarize_indexer_error(resp.status, error_text)
            logger.error(f"❌ API error {resp.status} for {url}: {detail}")
            _circuit_breaker.record_failure()
            return IndexerSubmitResult(
                ok=False,
                status_code=resp.status,
                detail=detail,
            )

    except Exception as e:
        exc_detail = _describe_exception(e)
        detail = _normalize_error_text(f"Indexer request failed: {exc_detail}")
        logger.error("❌ Failed to submit %s to API: %s", url, exc_detail)
        _circuit_breaker.record_failure()
        return IndexerSubmitResult(ok=False, detail=detail)
