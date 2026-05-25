import asyncio
import logging
import os
import tempfile
import time
from typing import Any

from web_search_contracts.admin_read_models import (
    CrawlerInstanceReadModel,
    CrawlerInstanceStatusReadModel,
    CrawlerInstancesReadModel,
)
from web_search_core.background import maintain_refresh_loop
from web_search_frontend.core.config import settings
from web_search_frontend.services.admin_cache import (
    build_singleflight,
    snapshot_timestamp,
)
from web_search_frontend.services.crawler_admin_client import fetch_admin_stats
from web_search_frontend.services.shared_json_cache import SharedJsonTtlCache

logger = logging.getLogger(__name__)

_SHARED_CRAWLER_INSTANCES_CACHE_PATH = os.path.join(
    tempfile.gettempdir(), "pbs-admin-crawler-instances-cache.json"
)
_crawler_instances_cache = SharedJsonTtlCache(
    _SHARED_CRAWLER_INSTANCES_CACHE_PATH,
    logger=logger,
    label="crawler instances cache",
)
_crawler_instances_build_lock = asyncio.Lock()


def _crawler_instances_cache_key(
    instances_config: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        {"name": inst.get("name", ""), "url": inst.get("url", "")}
        for inst in instances_config
    ]


def _clear_crawler_instances_memory_cache() -> None:
    _crawler_instances_cache.clear_memory()


def clear_crawler_instances_cache() -> None:
    _sync_crawler_instances_cache_path()
    _crawler_instances_cache.clear()


def _empty_crawler_instances_read_model() -> dict[str, Any]:
    return CrawlerInstancesReadModel().model_dump(mode="json")


def _present_crawler_instances_read_model(
    read_model: dict[str, Any], *, loaded_from: str
) -> dict[str, Any]:
    presented = dict(read_model)
    presented["snapshot_loaded_from"] = loaded_from
    return presented


def _get_memory_cached_crawler_instances_read_model(
    cache_key: list[dict[str, str]], now: float | None
) -> dict[str, Any] | None:
    return _crawler_instances_cache.get_memory(now=now, cache_key=cache_key)


def _get_shared_cached_crawler_instances_read_model(
    cache_key: list[dict[str, str]],
) -> dict[str, Any] | None:
    _sync_crawler_instances_cache_path()
    cached = _crawler_instances_cache.get_shared(
        cache_key=cache_key,
        validator=lambda data: isinstance(data, dict),
    )
    if cached is None:
        return None
    return cached


def _get_cached_crawler_instances_read_model_with_source(
    cache_key: list[dict[str, str]],
    now: float | None = None,
) -> tuple[str | None, dict[str, Any] | None]:
    cached = _get_memory_cached_crawler_instances_read_model(cache_key, now)
    if cached is not None:
        return "memory", cached

    shared_cached = _get_shared_cached_crawler_instances_read_model(cache_key)
    if shared_cached is not None:
        return "shared", shared_cached

    return None, None


def _set_cached_crawler_instances_read_model(
    cache_key: list[dict[str, str]], read_model: dict[str, Any]
) -> None:
    ttl = max(0, settings.ADMIN_DASHBOARD_CACHE_TTL_SEC)
    if ttl < 1:
        return

    _sync_crawler_instances_cache_path()
    _crawler_instances_cache.set(read_model, ttl, cache_key=cache_key)


def _sync_crawler_instances_cache_path() -> None:
    _crawler_instances_cache.path = _SHARED_CRAWLER_INSTANCES_CACHE_PATH


def _crawler_instances_build_singleflight():
    return build_singleflight(
        _crawler_instances_build_lock,
        cache_path=_SHARED_CRAWLER_INSTANCES_CACHE_PATH,
        label="crawler instances",
        logger=logger,
    )


async def get_crawler_instance_status(url: str) -> dict[str, Any]:
    status = CrawlerInstanceStatusReadModel().model_dump(mode="json")
    try:
        stats = await fetch_admin_stats(base_url=url)
        if stats is None:
            return status

        status = CrawlerInstanceStatusReadModel(
            state=stats.get("worker_status", "unknown"),
            frontier_pending=stats.get("frontier_pending", 0),
            uptime=stats.get("uptime_seconds"),
            concurrency=stats.get("concurrency"),
        ).model_dump(mode="json")
    except Exception as exc:
        logger.debug(f"Crawler instance {url} unreachable: {exc}")
    return status


async def _build_all_crawler_instances(
    instances_config: list[dict[str, str]],
) -> list[dict[str, Any]]:
    statuses = await asyncio.gather(
        *[get_crawler_instance_status(inst["url"]) for inst in instances_config]
    )
    return [
        CrawlerInstanceReadModel(
            name=inst["name"],
            url=inst["url"],
            **status,
        ).model_dump(mode="json")
        for inst, status in zip(instances_config, statuses, strict=False)
    ]


async def _build_crawler_instances_read_model(
    instances_config: list[dict[str, str]],
) -> dict[str, Any]:
    return CrawlerInstancesReadModel(
        instances=await _build_all_crawler_instances(instances_config),
        snapshot_generated_at=snapshot_timestamp(),
    ).model_dump(mode="json")


async def get_crawler_instances_read_model(
    instances_config: list[dict[str, str]],
) -> dict[str, Any]:
    cache_key = _crawler_instances_cache_key(instances_config)
    source, cached = _get_cached_crawler_instances_read_model_with_source(
        cache_key, time.monotonic()
    )
    if cached is not None:
        return _present_crawler_instances_read_model(
            cached, loaded_from=source or "memory"
        )

    async with _crawler_instances_build_singleflight():
        source, cached = _get_cached_crawler_instances_read_model_with_source(
            cache_key, time.monotonic()
        )
        if cached is not None:
            return _present_crawler_instances_read_model(
                cached, loaded_from=source or "shared"
            )

        read_model = await _build_crawler_instances_read_model(instances_config)
        _set_cached_crawler_instances_read_model(cache_key, read_model)
        return _present_crawler_instances_read_model(read_model, loaded_from="live")

    return _empty_crawler_instances_read_model()


async def get_all_crawler_instances(
    instances_config: list[dict[str, str]],
) -> list[dict[str, Any]]:
    read_model = await get_crawler_instances_read_model(instances_config)
    return read_model["instances"]


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

        _, cached = _get_cached_crawler_instances_read_model_with_source(
            cache_key, time.monotonic()
        )
        if cached is not None:
            logger.info("Crawler instances cache already warm")
            return

        async with _crawler_instances_build_singleflight():
            _, cached = _get_cached_crawler_instances_read_model_with_source(
                cache_key, time.monotonic()
            )
            if cached is not None:
                logger.info("Crawler instances cache already warm")
                return

            try:
                read_model = await _build_crawler_instances_read_model(instances_config)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Failed to prewarm crawler instances cache: %s", exc)
                _clear_crawler_instances_memory_cache()
                continue

            instances = read_model["instances"]
            if instances and all(
                inst.get("state") == "unreachable" for inst in instances
            ):
                _clear_crawler_instances_memory_cache()
                continue

            _set_cached_crawler_instances_read_model(cache_key, read_model)
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
