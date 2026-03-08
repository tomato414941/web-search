"""
Main Application Entry Point

FastAPI application factory and router registration.
"""

from fastapi import Depends, FastAPI
from app.api.deps import verify_api_key
from app.api.routes import crawl, worker, queue, history, seeds, stats
from app.api.routes.health import root_router as health_root_router
from app.core.events import lifespan
from app.core.config import settings


def create_app() -> FastAPI:
    """
    FastAPI application factory

    Creates and configures the FastAPI application with all routers.
    """
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Distributed web crawler service",
        lifespan=lifespan,
    )

    # Root-level health endpoints (Kubernetes probes) — no auth
    app.include_router(health_root_router, tags=["health"])

    # Register routers with /api/v1 prefix — require API key
    api_deps = [Depends(verify_api_key)]
    app.include_router(
        crawl.router, prefix="/api/v1", tags=["crawl"], dependencies=api_deps
    )
    app.include_router(
        worker.router, prefix="/api/v1/worker", tags=["worker"], dependencies=api_deps
    )
    app.include_router(
        queue.router, prefix="/api/v1", tags=["queue"], dependencies=api_deps
    )
    app.include_router(
        history.router, prefix="/api/v1", tags=["history"], dependencies=api_deps
    )
    app.include_router(
        seeds.router, prefix="/api/v1", tags=["seeds"], dependencies=api_deps
    )
    app.include_router(
        stats.router, prefix="/api/v1", tags=["stats"], dependencies=api_deps
    )

    return app


# Application instance
app = create_app()
