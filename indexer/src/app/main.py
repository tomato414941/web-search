"""
Indexer Service - FastAPI Application

Write-only service for indexing pages from the Crawler.
Implements CQRS pattern by separating write operations from read operations (Frontend).
"""

import asyncio
import logging
import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from shared.db.search import ensure_db
from shared.pagerank import calculate_pagerank, calculate_domain_pagerank
from app.api.routes import indexer, health
from app.api.routes.health import root_router as health_root_router

logger = logging.getLogger(__name__)


async def _pagerank_loop():
    """Background task: periodically recalculate page-level PageRank."""
    interval = settings.PAGERANK_INTERVAL_HOURS * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            count = calculate_pagerank(settings.DB_PATH)
            logger.info(f"Page PageRank recalculated: {count} pages")
        except Exception as e:
            logger.error(f"Page PageRank calculation failed: {e}")


async def _domain_rank_loop():
    """Background task: periodically recalculate domain-level PageRank."""
    interval = settings.DOMAIN_RANK_INTERVAL_HOURS * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            count = calculate_domain_pagerank(settings.DB_PATH)
            logger.info(f"Domain PageRank recalculated: {count} domains")
        except Exception as e:
            logger.error(f"Domain PageRank calculation failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: setup and teardown."""
    # --- DB Initialization ---
    db_dir = os.path.dirname(settings.DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    ensure_db(settings.DB_PATH)

    # --- Background PageRank tasks ---
    pr_task = asyncio.create_task(_pagerank_loop())
    dr_task = asyncio.create_task(_domain_rank_loop())

    yield

    pr_task.cancel()
    dr_task.cancel()


# --- FastAPI Application ---
app = FastAPI(
    lifespan=lifespan,
    title="Indexer Service",
    version=settings.APP_VERSION,
    description="Write-only service for indexing crawled pages (CQRS pattern).",
    openapi_tags=[
        {"name": "indexer", "description": "Page indexing endpoints"},
        {"name": "health", "description": "Health check endpoints"},
    ],
)

# --- CORS ---
cors_origins_env = os.getenv("CORS_ORIGINS")
if cors_origins_env:
    cors_origins = cors_origins_env.split(",")
else:
    # Development only - production must set CORS_ORIGINS
    cors_origins = ["http://localhost:8081"] if settings.DEBUG else []
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# --- Routers ---
# Root-level health endpoints (Kubernetes probes)
app.include_router(health_root_router, tags=["health"])

# Public health check (no auth, for load balancer) - backward compatibility
app.include_router(health.router, prefix="/api/v1", tags=["health"])

# Indexer API (requires API key)
app.include_router(indexer.router, prefix="/api/v1", tags=["indexer"])


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
