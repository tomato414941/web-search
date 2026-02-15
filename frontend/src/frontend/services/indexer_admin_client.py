import logging
from typing import Any

import httpx

from frontend.core.config import settings

logger = logging.getLogger(__name__)


def _default_health() -> dict[str, Any]:
    return {
        "reachable": False,
        "ok": False,
        "http_status": None,
        "error": None,
        "indexed_pages": 0,
        "pending_jobs": 0,
        "processing_jobs": 0,
        "done_jobs": 0,
        "failed_permanent_jobs": 0,
        "total_jobs": 0,
        "oldest_pending_seconds": 0,
    }


async def fetch_indexer_health() -> dict[str, Any]:
    """
    Fetch indexer health/stats from the internal indexer service.

    This call is server-side only to avoid exposing API keys in the browser.
    """
    result = _default_health()

    if not settings.INDEXER_API_KEY:
        result["error"] = "missing INDEXER_API_KEY"
        return result

    base_url = (settings.INDEXER_SERVICE_URL or "").rstrip("/")
    if not base_url:
        result["error"] = "missing INDEXER_SERVICE_URL"
        return result

    url = f"{base_url}/api/v1/indexer/health"
    headers = {"X-API-Key": settings.INDEXER_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
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
                "done_jobs",
                "failed_permanent_jobs",
                "total_jobs",
                "oldest_pending_seconds",
            ):
                if key in data and data.get(key) is not None:
                    result[key] = data[key]
    except Exception as exc:
        logger.warning("Failed to fetch indexer health: %s", exc)
        result["error"] = str(exc)

    return result
