"""
Application Lifecycle Events

Manages FastAPI lifespan events for startup and shutdown.
"""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from shared.core.infrastructure_config import Environment

logger = logging.getLogger(__name__)


async def _refresh_admin_caches() -> None:
    from app.api.deps import get_queue_service, get_seed_service
    from app.api.routes.seeds import prewarm_seeds_page_cache
    from app.api.routes.stats import prewarm_admin_stats_caches

    await asyncio.gather(
        prewarm_admin_stats_caches(get_queue_service()),
        prewarm_seeds_page_cache(get_seed_service()),
    )


async def maintain_admin_caches(*, refresh_interval_seconds: float) -> None:
    refresh_interval_seconds = max(1.0, refresh_interval_seconds)
    await asyncio.sleep(2)
    while True:
        try:
            await _refresh_admin_caches()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Failed to prewarm crawler admin caches", exc_info=True)
        else:
            logger.info("Prewarmed crawler admin caches")
        await asyncio.sleep(refresh_interval_seconds)


async def _prewarm_admin_caches() -> None:
    await maintain_admin_caches(refresh_interval_seconds=60)


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
    from app.workers.manager import worker_manager

    from app.core.config import settings

    # Initialize worker manager
    await worker_manager.initialize()
    prewarm_task: asyncio.Task[None] | None = None

    if settings.CRAWL_AUTO_START:
        await worker_manager.start(concurrency=settings.CRAWL_CONCURRENCY)
        logger.info(
            "Worker auto-started with concurrency=%d", settings.CRAWL_CONCURRENCY
        )
    else:
        logger.info("Worker manager initialized (workers not started)")
        logger.info("Use POST /worker/start to begin crawling")

    if settings.ENVIRONMENT != Environment.TEST:
        prewarm_task = asyncio.create_task(
            maintain_admin_caches(
                refresh_interval_seconds=settings.ADMIN_CACHE_REFRESH_SEC
            )
        )

    try:
        yield  # Application runs here
    finally:
        if prewarm_task is not None:
            prewarm_task.cancel()
            with suppress(asyncio.CancelledError):
                await prewarm_task

        # Shutdown
        logger.info("🛑 Shutting down Crawler Service...")
        await worker_manager.stop(graceful=True)

        from app.db.executor import shutdown_db_executor

        shutdown_db_executor()
        logger.info("✅ Shutdown complete")
