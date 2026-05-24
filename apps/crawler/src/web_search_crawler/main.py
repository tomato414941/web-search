"""
Main Application Entry Point

FastAPI application factory and router registration.
"""

from fastapi import Depends, FastAPI
from web_search_crawler.api.deps import verify_api_key
from web_search_crawler.api.routes import (
    crawl,
    crawl_attempts,
    frontier,
    worker,
    history,
    seeds,
)
from web_search_crawler.api.routes.health import root_router as health_root_router
from web_search_crawler.core.events import lifespan
from web_search_crawler.core.config import settings


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
        frontier.router, prefix="/api/v1", tags=["frontier"], dependencies=api_deps
    )
    app.include_router(
        crawl_attempts.router,
        prefix="/api/v1",
        tags=["crawl-attempts"],
        dependencies=api_deps,
    )
    app.include_router(
        history.router, prefix="/api/v1", tags=["history"], dependencies=api_deps
    )
    app.include_router(
        seeds.router, prefix="/api/v1", tags=["seeds"], dependencies=api_deps
    )
    return app


# Application instance
app = create_app()
