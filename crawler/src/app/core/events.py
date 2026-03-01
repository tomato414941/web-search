"""
Application Lifecycle Events

Manages FastAPI lifespan events for startup and shutdown.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
import logging

logger = logging.getLogger(__name__)


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

    if settings.CRAWL_AUTO_START:
        await worker_manager.start()
        logger.info("Worker manager initialized and workers auto-started")
    else:
        logger.info("Worker manager initialized (workers not started)")
        logger.info("Use POST /worker/start to begin crawling")

    yield  # Application runs here

    # Shutdown
    logger.info("🛑 Shutting down Crawler Service...")
    await worker_manager.stop(graceful=True)

    from app.db.executor import shutdown_db_executor

    shutdown_db_executor()
    logger.info("✅ Shutdown complete")
