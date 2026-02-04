"""
Health Check Router

Provides Kubernetes-compatible health check endpoints:
- /health: Simple health for load balancers
- /health/live: Liveness probe (process alive)
- /health/ready: Readiness probe (dependencies healthy)
"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db import Frontier
from app.core.config import settings

logger = logging.getLogger(__name__)

# Router for /api/v1 prefix (backward compatibility)
router = APIRouter()

# Router for root-level health endpoints
root_router = APIRouter()


def _check_db() -> bool:
    """Check PostgreSQL/SQLite connectivity."""
    try:
        frontier = Frontier(settings.CRAWLER_DB_PATH)
        frontier.size()
        return True
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        return False


def _check_frontier() -> bool:
    """Check frontier accessibility."""
    try:
        frontier = Frontier(settings.CRAWLER_DB_PATH)
        frontier.size()
        return True
    except Exception as e:
        logger.warning(f"Frontier health check failed: {e}")
        return False


# --- Root-level endpoints (Kubernetes probes) ---


@root_router.get("/health")
async def health():
    """Simple health check for load balancers."""
    return {"status": "ok"}


@root_router.get("/health/live")
async def liveness():
    """Kubernetes liveness probe - is the process running?"""
    return {"status": "ok"}


@root_router.get("/health/ready")
async def readiness():
    """Kubernetes readiness probe - are dependencies healthy?"""
    checks = {
        "database": "ok" if _check_db() else "unhealthy",
        "frontier": "ok" if _check_frontier() else "unhealthy",
    }

    all_healthy = all(v == "ok" for v in checks.values())
    status = "ok" if all_healthy else "unhealthy"

    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={"status": status, "checks": checks},
    )


# --- /api/v1 endpoints (backward compatibility) ---


@router.get("/health")
async def health_check():
    """Health check endpoint (backward compatible)."""
    return {"status": "ok"}
