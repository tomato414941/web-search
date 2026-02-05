"""
System Router

Provides Kubernetes-compatible health check endpoints:
- /health: Simple health for load balancers
- /health/live: Liveness probe (process alive)
- /health/ready: Readiness probe (dependencies healthy)
"""

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from frontend.core.config import settings
from frontend.core.db import get_connection

# Router for /api/v1 prefix (backward compatibility)
router = APIRouter()

# Router for root-level health endpoints
root_router = APIRouter()


def _check_database() -> bool:
    """Check database connectivity (PostgreSQL or SQLite)."""
    try:
        con = get_connection(settings.DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT 1")
        cur.close()
        con.close()
        return True
    except Exception:
        return False


def _check_crawler() -> bool:
    """Check Crawler service connectivity."""
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{settings.CRAWLER_SERVICE_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False


def _get_readiness_response():
    """Get readiness status with dependency checks."""
    checks = {
        "database": "ok" if _check_database() else "unhealthy",
        "crawler": "ok" if _check_crawler() else "unhealthy",
    }

    all_healthy = all(v == "ok" for v in checks.values())
    status = "ok" if all_healthy else "unhealthy"

    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={"status": status, "checks": checks},
    )


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
    return _get_readiness_response()


# Kubernetes-style short aliases
@root_router.get("/healthz")
async def healthz():
    """Liveness probe alias (/healthz)."""
    return {"ok": True}


@root_router.get("/readyz")
async def readyz():
    """Readiness probe alias (/readyz)."""
    return _get_readiness_response()


# --- /api/v1 endpoints (backward compatibility) ---


@router.get("/health")
async def health_check() -> dict:
    """Public health check endpoint for load balancer (backward compatible)."""
    return {"status": "ok", "service": "frontend"}
