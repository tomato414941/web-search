"""
Indexer Service - FastAPI Application

Write-only service for indexing pages from the Crawler.
Implements CQRS pattern by separating write operations from read operations (Frontend).
"""

import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from shared.db.search import ensure_db
from app.api.routes import indexer, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: setup and teardown."""
    # --- DB Initialization ---
    db_dir = os.path.dirname(settings.DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    ensure_db(settings.DB_PATH)
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
cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# --- Routers ---
# Public health check (no auth, for load balancer)
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
