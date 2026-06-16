"""
Application Lifecycle Events

Manages FastAPI lifespan events for startup and shutdown.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager

    Handles startup and shutdown events:
    - Startup: Initialize worker manager and start crawl workers
    - Shutdown: Stop running workers gracefully
    """
    logger.info("🚀 Starting Crawler Service...")

    # Import here to avoid circular dependencies
    from web_search_crawler.workers.manager import worker_manager

    from web_search_crawler.core.config import settings

    # Initialize worker manager
    await worker_manager.initialize()

    await worker_manager.start(concurrency=settings.CRAWL_CONCURRENCY)
    logger.info("Worker started with concurrency=%d", settings.CRAWL_CONCURRENCY)

    try:
        yield  # Application runs here
    finally:
        # Shutdown
        logger.info("🛑 Shutting down Crawler Service...")
        await worker_manager.stop(graceful=True)

        from web_search_crawler.db.executor import shutdown_db_executor

        shutdown_db_executor()
        logger.info("✅ Shutdown complete")
