import asyncio
import logging
from typing import Any

import httpx

from web_search_frontend.core.config import settings

logger = logging.getLogger(__name__)
_CRAWLER_REQUEST_TIMEOUT_SEC = 10.0


def _auth_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.INDEXER_API_KEY:
        headers["X-API-Key"] = settings.INDEXER_API_KEY
    return headers


class CrawlerApiError(Exception):
    pass


def _api_error(resp: httpx.Response) -> CrawlerApiError:
    return CrawlerApiError(f"Crawler API Error: {resp.text}")


def _crawler_base_url(base_url: str | None = None) -> str:
    return (base_url or settings.CRAWLER_SERVICE_URL).rstrip("/")


async def fetch_frontier_summary(
    *, base_url: str | None = None
) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=_CRAWLER_REQUEST_TIMEOUT_SEC) as client:
            resp = await client.get(
                f"{_crawler_base_url(base_url)}/api/v1/frontier/summary",
                headers=_auth_headers(),
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        logger.warning(f"Failed to get crawler frontier summary: {exc}")
    return None


async def fetch_worker_status(*, base_url: str | None = None) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=_CRAWLER_REQUEST_TIMEOUT_SEC) as client:
            resp = await client.get(
                f"{_crawler_base_url(base_url)}/api/v1/worker/status",
                headers=_auth_headers(),
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        logger.warning(f"Failed to get crawler worker status: {exc}")
    return None


async def fetch_dashboard_status(
    *, base_url: str | None = None
) -> dict[str, Any] | None:
    frontier, worker = await asyncio.gather(
        fetch_frontier_summary(base_url=base_url),
        fetch_worker_status(base_url=base_url),
    )
    if frontier is None and worker is None:
        return None

    worker_data = worker or {}
    return {
        "frontier_pending": (frontier or {}).get("pending", 0),
        "worker_status": worker_data.get("status", "unknown"),
    }


async def fetch_admin_stats(*, base_url: str | None = None) -> dict[str, Any] | None:
    frontier, worker = await asyncio.gather(
        fetch_frontier_summary(base_url=base_url),
        fetch_worker_status(base_url=base_url),
    )
    if frontier is None and worker is None:
        return None

    combined = {
        "frontier_pending": (frontier or {}).get("pending", 0),
    }
    worker_data = worker or {}
    combined["worker_status"] = worker_data.get("status", "unknown")
    combined["uptime_seconds"] = worker_data.get("uptime_seconds")
    combined["active_tasks"] = worker_data.get("active_tasks", 0)
    combined["concurrency"] = worker_data.get("concurrency")
    return combined


async def admit_url_to_frontier(url: str) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        payload = {"urls": [url]}
        resp = await client.post(
            f"{settings.CRAWLER_SERVICE_URL}/api/v1/urls",
            json=payload,
            headers=_auth_headers(),
        )
        if resp.status_code != 200:
            raise _api_error(resp)


async def crawl_now_url(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {"url": url}
        resp = await client.post(
            f"{settings.CRAWLER_SERVICE_URL}/api/v1/crawl-now",
            json=payload,
            headers=_auth_headers(),
        )
        if resp.status_code != 200:
            raise _api_error(resp)
        return resp.json()
