"""
Indexer Service

Submits crawled pages to the Indexer API.
"""

import json
import logging
from dataclasses import dataclass
import aiohttp

logger = logging.getLogger(__name__)

MAX_ERROR_DETAIL_LENGTH = 240


@dataclass(frozen=True)
class IndexerSubmitResult:
    ok: bool
    status_code: int | None = None
    detail: str | None = None
    job_id: str | None = None


def _normalize_error_text(text: str) -> str:
    normalized = " ".join(text.split())
    if len(normalized) > MAX_ERROR_DETAIL_LENGTH:
        return normalized[: MAX_ERROR_DETAIL_LENGTH - 3] + "..."
    return normalized


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

        async with session.post(
            api_url, json=payload, headers=headers, timeout=60
        ) as resp:
            if resp.status == 202:
                response_body = await resp.json()
                job_id = response_body.get("job_id")
                logger.info(f"✅ Queued for indexing: {url} (job_id={job_id})")
                return IndexerSubmitResult(
                    ok=True,
                    status_code=resp.status,
                    job_id=str(job_id) if job_id else None,
                )

            error_text = await resp.text()
            detail = _summarize_indexer_error(resp.status, error_text)
            logger.error(f"❌ API error {resp.status} for {url}: {detail}")
            return IndexerSubmitResult(
                ok=False,
                status_code=resp.status,
                detail=detail,
            )

    except Exception as e:
        detail = _normalize_error_text(f"Indexer request failed: {e}")
        logger.error(f"❌ Failed to submit {url} to API: {e}")
        return IndexerSubmitResult(ok=False, detail=detail)
