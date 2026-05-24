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


async def fetch_crawl_attempt_summary(
    *, base_url: str | None = None, hours: int = 1
) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=_CRAWLER_REQUEST_TIMEOUT_SEC) as client:
            resp = await client.get(
                f"{_crawler_base_url(base_url)}/api/v1/crawl-attempts/summary",
                params={"hours": hours},
                headers=_auth_headers(),
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        logger.warning(f"Failed to get crawler attempt summary: {exc}")
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
    frontier, attempts, worker = await asyncio.gather(
        fetch_frontier_summary(base_url=base_url),
        fetch_crawl_attempt_summary(base_url=base_url),
        fetch_worker_status(base_url=base_url),
    )
    if frontier is None and attempts is None and worker is None:
        return None

    attempt_data = attempts or {}
    combined = {
        "frontier_pending": (frontier or {}).get("pending", 0),
        "attempts_count_1h": attempt_data.get("attempts_count"),
        "submitted_count_1h": attempt_data.get("submitted_count"),
        "submit_rate_1h": attempt_data.get("submit_rate"),
        "error_count_1h": attempt_data.get("error_count"),
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


async def start_worker() -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/worker/start",
                headers=_auth_headers(),
            )
            if resp.status_code != 200:
                logger.warning(f"Failed to start crawler: {resp.text}")
    except httpx.RequestError as exc:
        logger.warning(f"Failed to start crawler: {exc}")


async def stop_worker() -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/worker/stop",
                json={},
                headers=_auth_headers(),
            )
            if resp.status_code != 200:
                logger.warning(f"Failed to stop crawler: {resp.text}")
    except httpx.RequestError as exc:
        logger.warning(f"Failed to stop crawler: {exc}")


async def start_crawler_instance(url: str, concurrency: int) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{url}/api/v1/worker/start",
                json={"concurrency": concurrency},
                headers=_auth_headers(),
            )
    except httpx.RequestError as exc:
        logger.warning(f"Failed to start crawler instance at {url}: {exc}")


async def stop_crawler_instance(url: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{url}/api/v1/worker/stop", json={}, headers=_auth_headers()
            )
    except httpx.RequestError as exc:
        logger.warning(f"Failed to stop crawler instance at {url}: {exc}")
