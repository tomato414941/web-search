"""
Application Lifecycle Events

Manages FastAPI lifespan events for startup and shutdown.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from web_search_crawler.db.executor import run_in_db_executor
from web_search_core.background import maintain_refresh_loop
from web_search_core.infrastructure_config import Environment

logger = logging.getLogger(__name__)

_crawl_schedule_maintenance_state: dict[str, object | None] = {
    "last_run_started_at": None,
    "last_run_completed_at": None,
    "last_reclaimed": 0,
    "total_reclaimed": 0,
    "last_error_at": None,
    "last_error": None,
}


def get_crawl_schedule_maintenance_state() -> dict[str, object | None]:
    return dict(_crawl_schedule_maintenance_state)


async def _reconcile_crawl_task_leases() -> int:
    from web_search_crawler.services.crawl_runtime import build_crawler_runtime_store

    return await run_in_db_executor(
        build_crawler_runtime_store().reconcile_expired_crawl_task_leases
    )


async def _reconcile_domain_state_inflight_leases() -> int:
    from web_search_crawler.services.crawl_runtime import build_crawler_runtime_store

    return await run_in_db_executor(
        build_crawler_runtime_store().reconcile_domain_state_inflight_leases
    )


async def maintain_crawl_schedule_health(*, refresh_interval_seconds: float) -> None:
    async def reconcile_once() -> None:
        now = int(time.time())
        _crawl_schedule_maintenance_state["last_run_started_at"] = now
        try:
            reclaimed, repaired = await asyncio.gather(
                _reconcile_crawl_task_leases(),
                _reconcile_domain_state_inflight_leases(),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            _crawl_schedule_maintenance_state["last_error_at"] = now
            _crawl_schedule_maintenance_state["last_error"] = "reconcile_failed"
            logger.warning(
                "Failed to reconcile crawler crawl task leases", exc_info=True
            )
        else:
            _crawl_schedule_maintenance_state["last_run_completed_at"] = now
            _crawl_schedule_maintenance_state["last_reclaimed"] = reclaimed
            _crawl_schedule_maintenance_state["total_reclaimed"] = (
                int(_crawl_schedule_maintenance_state["total_reclaimed"] or 0)
                + reclaimed
            )
            _crawl_schedule_maintenance_state["last_error"] = None
            if reclaimed:
                logger.info("Reclaimed %d expired crawl task lease(s)", reclaimed)
            if repaired:
                logger.info("Reconciled %d domain inflight lease row(s)", repaired)

    await maintain_refresh_loop(
        initial_call=reconcile_once,
        periodic_call=reconcile_once,
        refresh_interval_seconds=refresh_interval_seconds,
        initial_delay_seconds=2.0,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager

    Handles startup and shutdown events:
    - Startup: Initialize worker manager (but don't auto-start)
    - Shutdown: Stop running workers gracefully
    """
    logger.info("🚀 Starting Crawler Service...")

    # Import here to avoid circular dependencies
    from web_search_crawler.workers.manager import worker_manager

    from web_search_crawler.core.config import settings

    # Initialize worker manager
    await worker_manager.initialize()
    crawl_schedule_task: asyncio.Task[None] | None = None

    if settings.CRAWL_AUTO_START:
        await worker_manager.start(concurrency=settings.CRAWL_CONCURRENCY)
        logger.info(
            "Worker auto-started with concurrency=%d", settings.CRAWL_CONCURRENCY
        )
    else:
        logger.info("Worker manager initialized (workers not started)")
        logger.info("Use POST /worker/start to begin crawling")

    if settings.ENVIRONMENT != Environment.TEST:
        crawl_schedule_task = asyncio.create_task(
            maintain_crawl_schedule_health(
                refresh_interval_seconds=settings.CRAWL_SCHEDULE_MAINTENANCE_REFRESH_SEC
            )
        )

    try:
        yield  # Application runs here
    finally:
        if crawl_schedule_task is not None:
            crawl_schedule_task.cancel()
            with suppress(asyncio.CancelledError):
                await crawl_schedule_task

        # Shutdown
        logger.info("🛑 Shutting down Crawler Service...")
        await worker_manager.stop(graceful=True)

        from web_search_crawler.db.executor import shutdown_db_executor

        shutdown_db_executor()
        logger.info("✅ Shutdown complete")
