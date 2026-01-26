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
from shared.db.redis import get_redis
from app.core.config import settings

logger = logging.getLogger(__name__)

# Router for /api/v1 prefix (backward compatibility)
router = APIRouter()

# Router for root-level health endpoints
root_router = APIRouter()


def _check_redis() -> bool:
    """Check Redis connectivity."""
    try:
        r = get_redis()
        r.ping()
        return True
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        return False


def _check_queue() -> bool:
    """Check queue accessibility."""
    try:
        r = get_redis()
        r.zcard(settings.CRAWL_QUEUE_KEY)
        return True
    except Exception as e:
        logger.warning(f"Queue health check failed: {e}")
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
        "redis": "ok" if _check_redis() else "unhealthy",
        "queue": "ok" if _check_queue() else "unhealthy",
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
