import asyncio
import copy
import json
import logging
import math
import os
import tempfile
import time
from typing import Any

import httpx

from frontend.core.config import settings
from shared.core.background import maintain_refresh_loop

logger = logging.getLogger(__name__)

_crawler_instances_cache: dict[str, object] = {
    "data": None,
    "expires": 0.0,
    "key": None,
}
_SHARED_CRAWLER_INSTANCES_CACHE_PATH = os.path.join(
    tempfile.gettempdir(), "pbs-admin-crawler-instances-cache.json"
)


def _auth_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.INDEXER_API_KEY:
        headers["X-API-Key"] = settings.INDEXER_API_KEY
    return headers


class CrawlerApiError(Exception):
    pass


def _api_error(resp: httpx.Response) -> CrawlerApiError:
    return CrawlerApiError(f"Crawler API Error: {resp.text}")


def _crawler_instances_cache_key(
    instances_config: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        {"name": inst.get("name", ""), "url": inst.get("url", "")}
        for inst in instances_config
    ]


def _clear_crawler_instances_memory_cache() -> None:
    _crawler_instances_cache["data"] = None
    _crawler_instances_cache["expires"] = 0.0
    _crawler_instances_cache["key"] = None


def clear_crawler_instances_cache() -> None:
    _clear_crawler_instances_memory_cache()
    try:
        os.remove(_SHARED_CRAWLER_INSTANCES_CACHE_PATH)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("Failed to clear crawler instances cache: %s", exc)


def _serialize_crawler_instances(
    instances: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return json.loads(json.dumps(instances, default=str))


def _set_crawler_instances_memory_cache(
    cache_key: list[dict[str, str]], instances: list[dict[str, Any]], ttl: float
) -> None:
    if ttl < 1:
        return
    _crawler_instances_cache["data"] = copy.deepcopy(instances)
    _crawler_instances_cache["expires"] = time.monotonic() + ttl
    _crawler_instances_cache["key"] = copy.deepcopy(cache_key)


def _load_shared_crawler_instances_cache(
    cache_key: list[dict[str, str]],
) -> tuple[list[dict[str, Any]] | None, float]:
    try:
        with open(
            _SHARED_CRAWLER_INSTANCES_CACHE_PATH, "r", encoding="utf-8"
        ) as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return None, 0.0
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read crawler instances cache: %s", exc)
        return None, 0.0

    data = payload.get("data")
    expires_at = float(payload.get("expires_at", 0.0))
    stored_key = payload.get("cache_key")
    remaining_ttl = expires_at - time.time()
    if not isinstance(data, list) or stored_key != cache_key or remaining_ttl <= 0:
        return None, 0.0

    return data, remaining_ttl


def _get_memory_cached_crawler_instances(
    cache_key: list[dict[str, str]], now: float
) -> list[dict[str, Any]] | None:
    cached = _crawler_instances_cache["data"]
    if (
        cached is not None
        and _crawler_instances_cache["key"] == cache_key
        and now < float(_crawler_instances_cache["expires"])
    ):
        return copy.deepcopy(cached)  # type: ignore[arg-type]
    return None


def _get_shared_cached_crawler_instances(
    cache_key: list[dict[str, str]],
) -> list[dict[str, Any]] | None:
    cached, remaining_ttl = _load_shared_crawler_instances_cache(cache_key)
    if cached is None:
        return None

    _set_crawler_instances_memory_cache(cache_key, cached, remaining_ttl)
    return copy.deepcopy(cached)


def _write_shared_crawler_instances_cache(
    cache_key: list[dict[str, str]], instances: list[dict[str, Any]], ttl: float
) -> None:
    if ttl < 1:
        return

    payload = {
        "expires_at": time.time() + ttl,
        "cache_key": cache_key,
        "data": instances,
    }
    tmp_path = f"{_SHARED_CRAWLER_INSTANCES_CACHE_PATH}.{os.getpid()}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(tmp_path, _SHARED_CRAWLER_INSTANCES_CACHE_PATH)
    except OSError as exc:
        logger.warning("Failed to write crawler instances cache: %s", exc)
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _set_cached_crawler_instances(
    cache_key: list[dict[str, str]], instances: list[dict[str, Any]]
) -> None:
    ttl = max(0, settings.ADMIN_DASHBOARD_CACHE_TTL_SEC)
    if ttl < 1:
        return

    serialized = _serialize_crawler_instances(instances)
    _set_crawler_instances_memory_cache(cache_key, serialized, ttl)
    _write_shared_crawler_instances_cache(cache_key, serialized, ttl)


async def fetch_stats() -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/stats", headers=_auth_headers()
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        logger.warning(f"Failed to get crawler stats: {exc}")
    return None


async def fetch_status_breakdown(
    hours: int | None = None,
) -> dict[str, Any] | None:
    try:
        params = {"hours": hours} if hours is not None else {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/stats/breakdown",
                params=params,
                headers=_auth_headers(),
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        logger.warning(f"Failed to get status breakdown: {exc}")
    return None


async def fetch_seeds() -> list[dict[str, Any]]:
    """Backward-compatible helper returning the first seed page items."""
    return (await fetch_seeds_page())["items"]


async def fetch_seeds_page(
    page: int = 1, per_page: int = settings.ADMIN_SEEDS_PER_PAGE
) -> dict[str, Any]:
    page = max(1, page)
    per_page = max(1, per_page)
    offset = (page - 1) * per_page
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/seeds",
                params={"limit": per_page, "offset": offset, "include_total": "true"},
                headers=_auth_headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", []) if isinstance(data, dict) else data
                total = (
                    data.get("total", len(items))
                    if isinstance(data, dict)
                    else len(items)
                )
                last_page = max(1, math.ceil(total / per_page))
                return {
                    "items": items,
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "last_page": last_page,
                }
    except httpx.RequestError as exc:
        logger.warning(f"Failed to fetch seeds from crawler: {exc}")
    return {
        "items": [],
        "total": 0,
        "page": page,
        "per_page": per_page,
        "last_page": 1,
    }


async def fetch_frontier_stats() -> dict[str, Any] | None:
    """Fetch frontier health data from crawler."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/stats/frontier",
                headers=_auth_headers(),
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        logger.warning(f"Failed to get frontier stats: {exc}")
    return None


async def fetch_history(url_filter: str = "") -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {"url": url_filter} if url_filter else {}
            resp = await client.get(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/history",
                params=params,
                headers=_auth_headers(),
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
            headers=_auth_headers(),
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
            headers=_auth_headers(),
        )
        if resp.status_code != 200:
            raise _api_error(resp)


async def import_tranco(count: int) -> int:
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {"count": count}
        resp = await client.post(
            f"{settings.CRAWLER_SERVICE_URL}/api/v1/seeds/import-tranco",
            json=payload,
            headers=_auth_headers(),
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
            headers=_auth_headers(),
        )
        if resp.status_code != 200:
            raise _api_error(resp)


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
        headers = _auth_headers()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{url}/api/v1/stats", headers=headers)
            if resp.status_code != 200:
                return status

            stats = resp.json()
            status["state"] = stats.get("worker_status", "unknown")
            status["queue_size"] = stats.get("queue_size", 0)
            status["active_seen"] = stats.get("active_seen", 0)
            status["uptime"] = stats.get("uptime_seconds", stats.get("uptime"))
            status["concurrency"] = stats.get("concurrency")
            status["attempts_1h"] = stats.get(
                "attempts_count_1h",
                stats.get("crawl_rate_1h"),
            )
            status["indexed_1h"] = stats.get("indexed_count_1h")
            status["success_rate_1h"] = stats.get("success_rate_1h")
            status["error_1h"] = stats.get("error_count_1h")
    except httpx.RequestError as exc:
        logger.debug(f"Crawler instance {url} unreachable: {exc}")
    return status


async def _build_all_crawler_instances(
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


async def get_all_crawler_instances(
    instances_config: list[dict[str, str]],
) -> list[dict[str, Any]]:
    cache_key = _crawler_instances_cache_key(instances_config)
    cached = _get_memory_cached_crawler_instances(cache_key, time.monotonic())
    if cached is not None:
        return cached

    shared_cached = _get_shared_cached_crawler_instances(cache_key)
    if shared_cached is not None:
        return shared_cached

    instances = await _build_all_crawler_instances(instances_config)
    _set_cached_crawler_instances(cache_key, instances)
    return copy.deepcopy(instances)


async def prewarm_crawler_instances_cache(
    instances_config: list[dict[str, str]],
    *,
    attempts: int = 60,
    delay_seconds: float = 5.0,
) -> None:
    cache_key = _crawler_instances_cache_key(instances_config)
    for attempt in range(attempts):
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
        try:
            instances = await _build_all_crawler_instances(instances_config)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Failed to prewarm crawler instances cache: %s", exc)
            _clear_crawler_instances_memory_cache()
            continue

        if instances and all(inst.get("state") == "unreachable" for inst in instances):
            _clear_crawler_instances_memory_cache()
            continue

        _set_cached_crawler_instances(cache_key, instances)
        logger.info("Prewarmed crawler instances cache")
        return

    logger.warning("Crawler instances prewarm gave up after %d attempts", attempts)


async def maintain_crawler_instances_cache(
    instances_config: list[dict[str, str]], *, refresh_interval_seconds: float
) -> None:
    async def refresh_once() -> None:
        await prewarm_crawler_instances_cache(
            instances_config, attempts=1, delay_seconds=0
        )

    await maintain_refresh_loop(
        initial_call=lambda: prewarm_crawler_instances_cache(
            instances_config, delay_seconds=1.0
        ),
        periodic_call=refresh_once,
        refresh_interval_seconds=refresh_interval_seconds,
    )


def find_crawler_url(name: str, instances_config: list[dict[str, str]]) -> str | None:
    for inst in instances_config:
        if inst["name"] == name:
            return inst["url"]
    return None


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
