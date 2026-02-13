import asyncio
import logging
from typing import Any

import httpx

from frontend.core.config import settings

logger = logging.getLogger(__name__)


class CrawlerApiError(Exception):
    pass


def _api_error(resp: httpx.Response) -> CrawlerApiError:
    return CrawlerApiError(f"Crawler API Error: {resp.text}")


async def fetch_stats() -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.CRAWLER_SERVICE_URL}/api/v1/stats")
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        logger.warning(f"Failed to get crawler stats: {exc}")
    return None


async def fetch_seeds() -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.CRAWLER_SERVICE_URL}/api/v1/seeds")
            if resp.status_code == 200:
                return resp.json()
    except httpx.RequestError as exc:
        logger.warning(f"Failed to fetch seeds from crawler: {exc}")
    return []


async def fetch_queue(limit: int = 50) -> list[tuple[str, float]]:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/queue?limit={limit}"
            )
            if resp.status_code == 200:
                items = resp.json()
                return [(item["url"], item["score"]) for item in items]
    except httpx.RequestError as exc:
        logger.warning(f"Failed to fetch queue from crawler: {exc}")
    return []


async def fetch_history(url_filter: str = "") -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            params = {"url": url_filter} if url_filter else {}
            resp = await client.get(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/history",
                params=params,
            )
            if resp.status_code == 200:
                return resp.json()
    except httpx.RequestError as exc:
        logger.warning(f"Failed to fetch history from crawler: {exc}")
    return []


async def add_seed(url: str) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        payload = {"urls": [url]}
        resp = await client.post(
            f"{settings.CRAWLER_SERVICE_URL}/api/v1/seeds",
            json=payload,
        )
        if resp.status_code != 200:
            raise _api_error(resp)


async def delete_seed(url: str) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        payload = {"urls": [url]}
        resp = await client.request(
            "DELETE",
            f"{settings.CRAWLER_SERVICE_URL}/api/v1/seeds",
            json=payload,
        )
        if resp.status_code != 200:
            raise _api_error(resp)


async def import_tranco(count: int) -> int:
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {"count": count}
        resp = await client.post(
            f"{settings.CRAWLER_SERVICE_URL}/api/v1/seeds/import-tranco",
            json=payload,
        )
        if resp.status_code != 200:
            raise _api_error(resp)
        data = resp.json()
        return data.get("count", 0)


async def enqueue_url(url: str) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        payload = {"urls": [url]}
        resp = await client.post(
            f"{settings.CRAWLER_SERVICE_URL}/api/v1/urls",
            json=payload,
        )
        if resp.status_code != 200:
            raise _api_error(resp)


async def start_worker() -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/worker/start"
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
            )
            if resp.status_code != 200:
                logger.warning(f"Failed to stop crawler: {resp.text}")
    except httpx.RequestError as exc:
        logger.warning(f"Failed to stop crawler: {exc}")


async def get_crawler_instance_status(url: str) -> dict[str, Any]:
    status: dict[str, Any] = {
        "state": "unreachable",
        "queue_size": 0,
        "active_seen": 0,
        "uptime": None,
        "concurrency": None,
        "attempts_1h": None,
        "indexed_1h": None,
        "success_rate_1h": None,
        "error_1h": None,
    }
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{url}/api/v1/status")
            if resp.status_code == 200:
                data = resp.json()
                status["queue_size"] = data.get("queue_size", 0)
                status["active_seen"] = data.get("active_seen", 0)

            resp = await client.get(f"{url}/api/v1/worker/status")
            if resp.status_code == 200:
                worker = resp.json()
                status["state"] = worker.get("status", "unknown")
                status["uptime"] = worker.get("uptime", worker.get("uptime_seconds"))
                status["concurrency"] = worker.get("concurrency")

            resp = await client.get(f"{url}/api/v1/stats")
            if resp.status_code == 200:
                stats = resp.json()
                status["attempts_1h"] = stats.get(
                    "attempts_count_1h",
                    stats.get("crawl_rate_1h"),
                )
                status["indexed_1h"] = stats.get("indexed_count_1h")
                status["success_rate_1h"] = stats.get("success_rate_1h")
                status["error_1h"] = stats.get("error_count_1h")
                status["queue_size"] = stats.get("queue_size", status["queue_size"])
                status["active_seen"] = stats.get("active_seen", status["active_seen"])
                if status["state"] == "unreachable":
                    status["state"] = stats.get("worker_status", "unknown")
                if status["uptime"] is None:
                    status["uptime"] = stats.get("uptime_seconds")
                if status["concurrency"] is None:
                    status["concurrency"] = stats.get("concurrency")
    except httpx.RequestError as exc:
        logger.debug(f"Crawler instance {url} unreachable: {exc}")
    return status


async def get_all_crawler_instances(
    instances_config: list[dict[str, str]],
) -> list[dict[str, Any]]:
    statuses = await asyncio.gather(
        *[get_crawler_instance_status(inst["url"]) for inst in instances_config]
    )
    return [
        {
            "name": inst["name"],
            "url": inst["url"],
            **status,
        }
        for inst, status in zip(instances_config, statuses, strict=False)
    ]


def find_crawler_url(name: str, instances_config: list[dict[str, str]]) -> str | None:
    for inst in instances_config:
        if inst["name"] == name:
            return inst["url"]
    return None


async def start_crawler_instance(url: str, concurrency: int) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{url}/api/v1/worker/start", json={"concurrency": concurrency}
            )
    except httpx.RequestError as exc:
        logger.warning(f"Failed to start crawler instance at {url}: {exc}")


async def stop_crawler_instance(url: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{url}/api/v1/worker/stop", json={})
    except httpx.RequestError as exc:
        logger.warning(f"Failed to stop crawler instance at {url}: {exc}")
