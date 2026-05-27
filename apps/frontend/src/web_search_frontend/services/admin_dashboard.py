import asyncio
import logging
import os
import tempfile
import time
from typing import Any

from web_search_frontend.core.config import settings
from web_search_frontend.metrics import (
    record_admin_dashboard_cache_access,
    record_admin_dashboard_prewarm_result,
    set_admin_dashboard_last_prewarm_success,
)
from web_search_frontend.services.admin_cache import (
    build_singleflight,
    snapshot_timestamp,
)
from web_search_frontend.services.crawler_admin_client import fetch_dashboard_status
from web_search_frontend.services.shared_json_cache import SharedJsonTtlCache
from web_search_core.background import maintain_refresh_loop

logger = logging.getLogger(__name__)

_SHARED_CACHE_PATH = os.path.join(
    tempfile.gettempdir(), "pbs-admin-dashboard-cache.json"
)
_dashboard_cache = SharedJsonTtlCache(
    _SHARED_CACHE_PATH,
    logger=logger,
    label="shared admin dashboard cache",
)
_dashboard_build_lock = asyncio.Lock()


def _empty_dashboard_data() -> dict[str, Any]:
    return {
        "indexed_documents": None,
        "worker_status": "unknown",
        "health": {"level": "ok", "messages": []},
        "snapshot_generated_at": None,
        "snapshot_loaded_from": "empty",
    }


def _clear_dashboard_memory_cache() -> None:
    _dashboard_cache.clear_memory()


def _clear_dashboard_cache() -> None:
    _sync_dashboard_cache_path()
    _dashboard_cache.clear()


def clear_dashboard_cache() -> None:
    _clear_dashboard_cache()


def _get_memory_cached_dashboard_data(now: float) -> dict[str, Any] | None:
    return _dashboard_cache.get_memory(now=now)


def _get_shared_cached_dashboard_data() -> dict[str, Any] | None:
    _sync_dashboard_cache_path()
    cached = _dashboard_cache.get_shared(validator=lambda data: isinstance(data, dict))
    if cached is None:
        return None
    return cached


def _get_cached_dashboard_data(now: float) -> dict[str, Any] | None:
    _, cached = _get_cached_dashboard_data_with_source(now)
    return cached


def _get_cached_dashboard_data_with_source(
    now: float,
) -> tuple[str | None, dict[str, Any] | None]:
    cached = _get_memory_cached_dashboard_data(now)
    if cached is not None:
        return "memory", cached

    shared_cached = _get_shared_cached_dashboard_data()
    if shared_cached is not None:
        return "shared", shared_cached

    return None, None


def _present_dashboard_data(
    data: dict[str, Any], *, loaded_from: str
) -> dict[str, Any]:
    presented = dict(data)
    presented["snapshot_loaded_from"] = loaded_from
    return presented


def _set_cached_dashboard_data(data: dict[str, Any]) -> None:
    ttl = max(0, settings.ADMIN_DASHBOARD_CACHE_TTL_SEC)
    if ttl < 1:
        return

    _sync_dashboard_cache_path()
    _dashboard_cache.set(data, ttl)


def _sync_dashboard_cache_path() -> None:
    _dashboard_cache.path = _SHARED_CACHE_PATH


def _dashboard_build_singleflight():
    return build_singleflight(
        _dashboard_build_lock,
        cache_path=_SHARED_CACHE_PATH,
        label="admin dashboard",
        logger=logger,
    )


def _get_search_index_dashboard_data() -> dict[str, Any]:
    try:
        from web_search_opensearch.client import INDEX_NAME, get_client

        client = get_client(settings.OPENSEARCH_URL)
        count = client.count(index=INDEX_NAME)["count"]
        return {"indexed_documents": int(count)}
    except Exception as exc:
        logger.warning("Failed to get OpenSearch document count: %s", exc)
        return {"indexed_documents": None}


async def _build_dashboard_data() -> dict[str, Any]:
    data = _empty_dashboard_data()
    index_data, stats = await asyncio.gather(
        asyncio.to_thread(_get_search_index_dashboard_data),
        fetch_dashboard_status(),
    )
    data.update(index_data)

    crawler_reachable = False
    if stats:
        crawler_reachable = True
        data["worker_status"] = stats.get("worker_status", "unknown")

    health_messages: list[str] = []
    if not crawler_reachable:
        health_messages.append("Crawler service is unreachable")
        data["health"]["level"] = "error"
    elif data["worker_status"] == "stopped":
        health_messages.append("Crawler is stopped. Indexing paused.")
        data["health"]["level"] = "warning"

    data["health"]["messages"] = health_messages
    data["snapshot_generated_at"] = snapshot_timestamp()
    return data


async def get_dashboard_data() -> dict[str, Any]:
    source, cached = _get_cached_dashboard_data_with_source(time.monotonic())
    if cached is not None:
        record_admin_dashboard_cache_access(source or "memory")
        return _present_dashboard_data(cached, loaded_from=source or "memory")

    async with _dashboard_build_singleflight():
        source, cached = _get_cached_dashboard_data_with_source(time.monotonic())
        if cached is not None:
            record_admin_dashboard_cache_access(source or "shared")
            return _present_dashboard_data(cached, loaded_from=source or "shared")

        record_admin_dashboard_cache_access("miss")
        data = await _build_dashboard_data()
        _set_cached_dashboard_data(data)
        return _present_dashboard_data(data, loaded_from="live")


async def prewarm_dashboard_cache(
    *, attempts: int = 60, delay_seconds: float = 5.0
) -> None:
    for attempt in range(attempts):
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

        cached = _get_cached_dashboard_data(time.monotonic())
        if cached is not None and cached.get("worker_status") != "unknown":
            record_admin_dashboard_prewarm_result("success")
            set_admin_dashboard_last_prewarm_success()
            logger.info("Admin dashboard cache already warm")
            return

        async with _dashboard_build_singleflight():
            cached = _get_cached_dashboard_data(time.monotonic())
            if cached is not None and cached.get("worker_status") != "unknown":
                record_admin_dashboard_prewarm_result("success")
                set_admin_dashboard_last_prewarm_success()
                logger.info("Admin dashboard cache already warm")
                return

            try:
                data = await _build_dashboard_data()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Failed to prewarm admin dashboard cache: %s", exc)
                record_admin_dashboard_prewarm_result("error")
                _clear_dashboard_memory_cache()
                continue

            if data["worker_status"] == "unknown":
                record_admin_dashboard_prewarm_result("skipped")
                _clear_dashboard_memory_cache()
                continue

            _set_cached_dashboard_data(data)
            record_admin_dashboard_prewarm_result("success")
            set_admin_dashboard_last_prewarm_success()
            logger.info("Prewarmed admin dashboard cache")
            return

    record_admin_dashboard_prewarm_result("gave_up")
    logger.warning("Admin dashboard prewarm gave up after %d attempts", attempts)


async def maintain_dashboard_cache(*, refresh_interval_seconds: float) -> None:
    async def refresh_once() -> None:
        await prewarm_dashboard_cache(attempts=1, delay_seconds=0)

    await maintain_refresh_loop(
        initial_call=prewarm_dashboard_cache,
        periodic_call=refresh_once,
        refresh_interval_seconds=refresh_interval_seconds,
    )
