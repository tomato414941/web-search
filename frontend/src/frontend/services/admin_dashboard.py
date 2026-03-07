import asyncio
import copy
import json
import logging
import os
import tempfile
import time
from typing import Any

from frontend.core.config import settings
from frontend.api.metrics import (
    record_admin_dashboard_cache_access,
    record_admin_dashboard_prewarm_result,
    set_admin_dashboard_last_prewarm_success,
)
from frontend.services.admin_analytics import (
    build_analytics_exclusion_filters,
    time_boundaries,
)
from frontend.services.crawler_admin_client import fetch_stats, fetch_status_breakdown
from shared.core.background import maintain_refresh_loop
from shared.postgres.search import get_connection
from shared.postgres.repositories.analytics_repo import AnalyticsRepository

logger = logging.getLogger(__name__)

_repo = AnalyticsRepository
_dashboard_cache: dict[str, object] = {"data": None, "expires": 0.0}
_SHARED_CACHE_PATH = os.path.join(
    tempfile.gettempdir(), "pbs-admin-dashboard-cache.json"
)


def _empty_dashboard_data() -> dict[str, Any]:
    return {
        "indexed_pages": 0,
        "indexed_delta": 0,
        "queue_size": 0,
        "visited_count": 0,
        "last_crawl": None,
        "worker_status": "unknown",
        "uptime_seconds": None,
        "active_tasks": 0,
        "recent_error_count": 0,
        "crawl_rate": 0,
        "today_searches": 0,
        "today_unique_queries": 0,
        "today_zero_hits": 0,
        "zero_hit_rate": 0.0,
        "top_query": None,
        "zero_hit_queries": [],
        "recent_errors": [],
        "status_breakdown": None,
        "health": {"level": "ok", "messages": []},
    }


def _clear_dashboard_memory_cache() -> None:
    _dashboard_cache["data"] = None
    _dashboard_cache["expires"] = 0.0


def _clear_dashboard_cache() -> None:
    _clear_dashboard_memory_cache()
    try:
        os.remove(_SHARED_CACHE_PATH)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("Failed to clear shared admin dashboard cache: %s", exc)


def _serialize_dashboard_data(data: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(data, default=str))


def _set_memory_cache(data: dict[str, Any], ttl: float) -> None:
    if ttl < 1:
        return
    _dashboard_cache["data"] = copy.deepcopy(data)
    _dashboard_cache["expires"] = time.monotonic() + ttl


def _load_shared_dashboard_cache() -> tuple[dict[str, Any] | None, float]:
    try:
        with open(_SHARED_CACHE_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return None, 0.0
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read shared admin dashboard cache: %s", exc)
        return None, 0.0

    data = payload.get("data")
    expires_at = float(payload.get("expires_at", 0.0))
    remaining_ttl = expires_at - time.time()
    if not isinstance(data, dict) or remaining_ttl <= 0:
        return None, 0.0

    return data, remaining_ttl


def _get_memory_cached_dashboard_data(now: float) -> dict[str, Any] | None:
    cached = _dashboard_cache["data"]
    if cached is not None and now < float(_dashboard_cache["expires"]):
        return copy.deepcopy(cached)  # type: ignore[arg-type]
    return None


def _get_shared_cached_dashboard_data() -> dict[str, Any] | None:
    shared_cached, remaining_ttl = _load_shared_dashboard_cache()
    if shared_cached is None:
        return None

    _set_memory_cache(shared_cached, remaining_ttl)
    return copy.deepcopy(shared_cached)


def _write_shared_dashboard_cache(data: dict[str, Any], ttl: float) -> None:
    if ttl < 1:
        return

    payload = {"expires_at": time.time() + ttl, "data": data}
    tmp_path = f"{_SHARED_CACHE_PATH}.{os.getpid()}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(tmp_path, _SHARED_CACHE_PATH)
    except OSError as exc:
        logger.warning("Failed to write shared admin dashboard cache: %s", exc)
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _get_cached_dashboard_data(now: float) -> dict[str, Any] | None:
    cached = _get_memory_cached_dashboard_data(now)
    if cached is not None:
        return cached

    return _get_shared_cached_dashboard_data()


def _set_cached_dashboard_data(data: dict[str, Any]) -> None:
    ttl = max(0, settings.ADMIN_DASHBOARD_CACHE_TTL_SEC)
    if ttl < 1:
        return

    serialized = _serialize_dashboard_data(data)
    _set_memory_cache(serialized, ttl)
    _write_shared_dashboard_cache(serialized, ttl)


def _get_db_dashboard_data() -> dict[str, Any]:
    data: dict[str, Any] = {
        "indexed_pages": 0,
        "indexed_delta": 0,
        "last_crawl": None,
        "today_searches": 0,
        "today_unique_queries": 0,
        "today_zero_hits": 0,
        "zero_hit_rate": 0.0,
        "top_query": None,
        "zero_hit_queries": [],
    }

    try:
        day_ago, _, today_start = time_boundaries()
        search_filter_sql, search_filter_params = build_analytics_exclusion_filters()
        conn = get_connection(settings.DB_PATH)
        try:
            document_summary = _repo.document_summary(conn, day_ago)
            data["indexed_pages"] = document_summary["total_documents"]
            data["indexed_delta"] = document_summary["indexed_since"]
            data["last_crawl"] = document_summary["max_indexed_at"]

            summary = _repo.today_summary(
                conn, today_start, search_filter_sql, search_filter_params
            )
            data["today_searches"] = summary["total"]
            data["today_unique_queries"] = summary["unique_queries"]
            data["today_zero_hits"] = summary["zero_hits"]
            if data["today_searches"] > 0:
                data["zero_hit_rate"] = round(
                    data["today_zero_hits"] / data["today_searches"] * 100,
                    1,
                )

            top = _repo.top_queries(
                conn, today_start, 1, search_filter_sql, search_filter_params
            )
            if top:
                data["top_query"] = {"query": top[0]["query"], "count": top[0]["count"]}

            data["zero_hit_queries"] = _repo.zero_hit_queries(
                conn, today_start, 5, search_filter_sql, search_filter_params
            )
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(f"Failed to get DB stats: {exc}")

    return data


async def _build_dashboard_data() -> dict[str, Any]:
    data = _empty_dashboard_data()
    db_data, data["status_breakdown"], stats = await asyncio.gather(
        asyncio.to_thread(_get_db_dashboard_data),
        fetch_status_breakdown(),
        fetch_stats(),
    )
    data.update(db_data)

    crawler_reachable = False
    if stats:
        crawler_reachable = True
        data["queue_size"] = stats.get("queue_size", 0)
        data["visited_count"] = stats.get("active_seen", 0)
        data["worker_status"] = stats.get("worker_status", "unknown")
        data["uptime_seconds"] = stats.get("uptime_seconds")
        data["active_tasks"] = stats.get("active_tasks", 0)
        data["crawl_rate"] = stats.get("crawl_rate_1h", 0)
        data["recent_error_count"] = stats.get("error_count_1h", 0)
        data["recent_errors"] = stats.get("recent_errors", [])

    health_messages: list[str] = []
    if not crawler_reachable:
        health_messages.append("Crawler service is unreachable")
        data["health"]["level"] = "error"
    elif data["worker_status"] == "stopped":
        health_messages.append("Crawler is stopped. Indexing paused.")
        data["health"]["level"] = "warning"
    elif data["queue_size"] == 0 and data["worker_status"] == "running":
        health_messages.append("Queue is empty. Waiting for new URLs.")
        data["health"]["level"] = "warning"

    if data["zero_hit_rate"] > 50 and data["today_searches"] >= 10:
        health_messages.append(
            f"High zero-hit rate: {data['zero_hit_rate']}% of searches returned no results"
        )
        if data["health"]["level"] == "ok":
            data["health"]["level"] = "warning"

    data["health"]["messages"] = health_messages
    return data


async def get_dashboard_data() -> dict[str, Any]:
    now = time.monotonic()
    cached = _get_memory_cached_dashboard_data(now)
    if cached is not None:
        record_admin_dashboard_cache_access("memory")
        return cached

    shared_cached = _get_shared_cached_dashboard_data()
    if shared_cached is not None:
        record_admin_dashboard_cache_access("shared")
        return shared_cached

    record_admin_dashboard_cache_access("miss")
    data = await _build_dashboard_data()
    _set_cached_dashboard_data(data)
    return copy.deepcopy(data)


async def prewarm_dashboard_cache(
    *, attempts: int = 60, delay_seconds: float = 5.0
) -> None:
    for attempt in range(attempts):
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
        try:
            data = await _build_dashboard_data()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Failed to prewarm admin dashboard cache: %s", exc)
            record_admin_dashboard_prewarm_result("error")
            _clear_dashboard_memory_cache()
            continue

        if data["worker_status"] == "unknown" or data["status_breakdown"] is None:
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
