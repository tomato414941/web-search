import logging
from typing import Any

import httpx

from frontend.core.config import settings

logger = logging.getLogger(__name__)


def _default_stats() -> dict[str, Any]:
    return {
        "reachable": False,
        "ok": False,
        "http_status": None,
        "error": None,
        "indexed_pages": 0,
        "pending_jobs": 0,
        "processing_jobs": 0,
        "failed_permanent_jobs": 0,
    }


async def fetch_indexer_stats() -> dict[str, Any]:
    """
    Fetch indexer stats from the internal indexer service.

    This call is server-side only to avoid exposing API keys in the browser.
    """
    result = _default_stats()

    if not settings.INDEXER_API_KEY:
        result["error"] = "missing INDEXER_API_KEY"
        return result

    base_url = (settings.INDEXER_SERVICE_URL or "").rstrip("/")
    if not base_url:
        result["error"] = "missing INDEXER_SERVICE_URL"
        return result

    url = f"{base_url}/api/v1/indexer/stats"
    headers = {"X-API-Key": settings.INDEXER_API_KEY}
    try:
        async with httpx.AsyncClient(
            timeout=settings.INDEXER_ADMIN_TIMEOUT_SEC
        ) as client:
            resp = await client.get(url, headers=headers)
            result["http_status"] = resp.status_code
            if resp.status_code != 200:
                result["error"] = f"indexer returned {resp.status_code}"
                return result

            data = resp.json()
            result["reachable"] = True
            result["ok"] = bool(data.get("ok"))
            for key in (
                "indexed_pages",
                "pending_jobs",
                "processing_jobs",
                "failed_permanent_jobs",
            ):
                if key in data and data.get(key) is not None:
                    result[key] = data[key]
    except Exception as exc:
        logger.warning("Failed to fetch indexer stats: %s", exc)
        result["error"] = str(exc)

    return result


async def fetch_failed_jobs(limit: int = 50) -> list[dict[str, Any]]:
    """Fetch permanently failed indexing jobs from the indexer service."""
    if not settings.INDEXER_API_KEY:
        return []

    base_url = (settings.INDEXER_SERVICE_URL or "").rstrip("/")
    if not base_url:
        return []

    url = f"{base_url}/api/v1/indexer/jobs/failed?limit={limit}"
    headers = {"X-API-Key": settings.INDEXER_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("jobs", [])
    except Exception as exc:
        logger.warning("Failed to fetch failed jobs: %s", exc)

    return []


async def retry_failed_job(job_id: str) -> bool:
    """Retry a permanently failed job via the indexer service."""
    if not settings.INDEXER_API_KEY:
        return False

    base_url = (settings.INDEXER_SERVICE_URL or "").rstrip("/")
    if not base_url:
        return False

    url = f"{base_url}/api/v1/indexer/jobs/{job_id}/retry"
    headers = {"X-API-Key": settings.INDEXER_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, headers=headers)
            return resp.status_code == 200
    except Exception as exc:
        logger.warning("Failed to retry job %s: %s", job_id, exc)

    return False
