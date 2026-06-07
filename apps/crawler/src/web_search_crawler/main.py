"""
Main Application Entry Point

FastAPI application factory and router registration.
"""

from fastapi import FastAPI
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
    return app


# Application instance
app = create_app()
