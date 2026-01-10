"""
Main Application Entry Point

FastAPI application factory and router registration.
"""

from fastapi import FastAPI
from app.api.routes import health, crawl, worker, queue, history, scoring
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

    # Register routers
    app.include_router(health.router, tags=["health"])
    app.include_router(crawl.router, tags=["crawl"])
    app.include_router(worker.router, prefix="/worker", tags=["worker"])
    app.include_router(queue.router, tags=["queue"])
    app.include_router(history.router, tags=["history"])
    app.include_router(scoring.router, tags=["scoring"])

    return app


# Application instance
app = create_app()
