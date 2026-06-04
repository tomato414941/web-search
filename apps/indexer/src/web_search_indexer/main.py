"""Indexer Service - FastAPI Application (API-only)."""

import logging
import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web_search_indexer.core.config import settings
from web_search_indexer.metrics import router as metrics_router
from web_search_postgres.migrate import migrate
from web_search_indexer.api.routes import indexer
from web_search_indexer.api.routes.health import root_router as health_root_router
from web_search_indexer.services.index_job_container import configure_index_job_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: setup and teardown."""
    if settings.RUN_MIGRATIONS:
        migrate()

    configure_index_job_service()
    yield


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
app.include_router(metrics_router, tags=["metrics"], include_in_schema=False)

# Indexer API (requires API key)
app.include_router(indexer.router, tags=["indexer"])


if __name__ == "__main__":
    uvicorn.run(
        "web_search_indexer.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
