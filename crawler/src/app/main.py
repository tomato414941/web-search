"""
Main Application Entry Point

FastAPI application factory and router registration.
"""

from fastapi import FastAPI
from app.api.routes import health, crawl, worker, queue, history, scoring, seeds, stats
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

    # Root-level health endpoints (Kubernetes probes)
    app.include_router(health_root_router, tags=["health"])

    # Register routers with /api/v1 prefix
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(crawl.router, prefix="/api/v1", tags=["crawl"])
    app.include_router(worker.router, prefix="/api/v1/worker", tags=["worker"])
    app.include_router(queue.router, prefix="/api/v1", tags=["queue"])
    app.include_router(history.router, prefix="/api/v1", tags=["history"])
    app.include_router(scoring.router, prefix="/api/v1", tags=["scoring"])
    app.include_router(seeds.router, prefix="/api/v1", tags=["seeds"])
    app.include_router(stats.router, prefix="/api/v1", tags=["stats"])

    return app


# Application instance
app = create_app()
