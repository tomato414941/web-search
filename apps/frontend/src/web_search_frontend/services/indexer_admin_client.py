import asyncio
import logging
import os
import tempfile
import time
from typing import Any

import httpx

from web_search_frontend.core.config import settings
from web_search_frontend.services.admin_cache import (
    build_singleflight,
    snapshot_timestamp,
)
from web_search_frontend.services.shared_json_cache import SharedJsonTtlCache
from web_search_contracts.admin_read_models import (
    IndexerAdminReadModel,
    IndexerFailedJobReadModel,
    IndexerHealthReadModel,
)
from web_search_core.background import maintain_refresh_loop

logger = logging.getLogger(__name__)
_SHARED_INDEXER_CACHE_PATH = os.path.join(
    tempfile.gettempdir(), "pbs-admin-indexer-cache.json"
)
_indexer_admin_cache = SharedJsonTtlCache(
    _SHARED_INDEXER_CACHE_PATH,
    logger=logger,
    label="shared admin indexer cache",
)
_indexer_build_lock = asyncio.Lock()


def _default_stats() -> dict[str, Any]:
    return IndexerHealthReadModel().model_dump(mode="json")


def _empty_indexer_admin_read_model() -> dict[str, Any]:
    return IndexerAdminReadModel().model_dump(mode="json")


def _sync_indexer_cache_path() -> None:
    _indexer_admin_cache.path = _SHARED_INDEXER_CACHE_PATH


def clear_indexer_admin_cache() -> None:
    _sync_indexer_cache_path()
    _indexer_admin_cache.clear()


def _get_memory_cached_indexer_admin_read_model(now: float) -> dict[str, Any] | None:
    return _indexer_admin_cache.get_memory(now=now)


def _get_shared_cached_indexer_admin_read_model() -> dict[str, Any] | None:
    _sync_indexer_cache_path()
    cached = _indexer_admin_cache.get_shared(
        validator=lambda data: isinstance(data, dict)
    )
    if cached is None:
        return None
    return cached


def _get_cached_indexer_admin_read_model_with_source(
    now: float,
) -> tuple[str | None, dict[str, Any] | None]:
    cached = _get_memory_cached_indexer_admin_read_model(now)
    if cached is not None:
        return "memory", cached

    shared_cached = _get_shared_cached_indexer_admin_read_model()
    if shared_cached is not None:
        return "shared", shared_cached

    return None, None


def _present_indexer_admin_read_model(
    read_model: dict[str, Any], *, loaded_from: str
) -> dict[str, Any]:
    presented = dict(read_model)
    presented["snapshot_loaded_from"] = loaded_from
    return presented


def _set_cached_indexer_admin_read_model(read_model: dict[str, Any]) -> None:
    ttl = max(0, settings.ADMIN_DASHBOARD_CACHE_TTL_SEC)
    if ttl < 1:
        return

    _sync_indexer_cache_path()
    _indexer_admin_cache.set(read_model, ttl)


def _indexer_build_singleflight():
    return build_singleflight(
        _indexer_build_lock,
        cache_path=_SHARED_INDEXER_CACHE_PATH,
        label="admin indexer",
        logger=logger,
    )


async def fetch_indexer_stats() -> dict[str, Any]:
    """
    Fetch indexer stats from the internal indexer service.

    This call is server-side only to avoid exposing API keys in the browser.
    """
    result = _default_stats()

    if not settings.INDEXER_API_KEY:
        result["error"] = "missing INDEXER_API_KEY"
        return IndexerHealthReadModel.model_validate(result).model_dump(mode="json")

    base_url = (settings.INDEXER_SERVICE_URL or "").rstrip("/")
    if not base_url:
        result["error"] = "missing INDEXER_SERVICE_URL"
        return IndexerHealthReadModel.model_validate(result).model_dump(mode="json")

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
                return IndexerHealthReadModel.model_validate(result).model_dump(
                    mode="json"
                )

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

    return IndexerHealthReadModel.model_validate(result).model_dump(mode="json")


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
                jobs = data.get("jobs", [])
                return [
                    IndexerFailedJobReadModel.model_validate(job).model_dump(
                        mode="json"
                    )
                    for job in jobs
                ]
    except Exception as exc:
        logger.warning("Failed to fetch failed jobs: %s", exc)

    return []


async def _build_indexer_admin_read_model() -> dict[str, Any]:
    health, failed_jobs = await asyncio.gather(
        fetch_indexer_stats(),
        fetch_failed_jobs(limit=50),
    )
    return IndexerAdminReadModel(
        health=health,
        failed_jobs=failed_jobs,
        snapshot_generated_at=snapshot_timestamp(),
    ).model_dump(mode="json")


async def get_indexer_admin_read_model() -> dict[str, Any]:
    source, cached = _get_cached_indexer_admin_read_model_with_source(time.monotonic())
    if cached is not None:
        return _present_indexer_admin_read_model(cached, loaded_from=source or "memory")

    async with _indexer_build_singleflight():
        source, cached = _get_cached_indexer_admin_read_model_with_source(
            time.monotonic()
        )
        if cached is not None:
            return _present_indexer_admin_read_model(
                cached, loaded_from=source or "memory"
            )

        read_model = await _build_indexer_admin_read_model()
        _set_cached_indexer_admin_read_model(read_model)
        return _present_indexer_admin_read_model(read_model, loaded_from="live")

    return _empty_indexer_admin_read_model()


async def prewarm_indexer_admin_cache(
    *, attempts: int = 60, delay_seconds: float = 5.0
) -> None:
    for _ in range(attempts):
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

        _, cached = _get_cached_indexer_admin_read_model_with_source(time.monotonic())
        if cached is not None:
            logger.info("Admin indexer cache already warm")
            return

        async with _indexer_build_singleflight():
            _, cached = _get_cached_indexer_admin_read_model_with_source(
                time.monotonic()
            )
            if cached is not None:
                logger.info("Admin indexer cache already warm")
                return

            try:
                read_model = await _build_indexer_admin_read_model()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Failed to prewarm admin indexer cache: %s", exc)
                continue

            _set_cached_indexer_admin_read_model(read_model)
            logger.info("Prewarmed admin indexer cache")
            return

    logger.warning("Admin indexer prewarm gave up after %d attempts", attempts)


async def maintain_indexer_admin_cache(*, refresh_interval_seconds: float) -> None:
    async def refresh_once() -> None:
        await prewarm_indexer_admin_cache(attempts=1, delay_seconds=0)

    await maintain_refresh_loop(
        initial_call=prewarm_indexer_admin_cache,
        periodic_call=refresh_once,
        refresh_interval_seconds=refresh_interval_seconds,
    )


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
            if resp.status_code == 200:
                clear_indexer_admin_cache()
                return True
            return False
    except Exception as exc:
        logger.warning("Failed to retry job %s: %s", job_id, exc)

    return False
