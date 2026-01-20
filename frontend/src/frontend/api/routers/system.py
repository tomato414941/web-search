"""
System Router

Provides Kubernetes-compatible health check endpoints:
- /health: Simple health for load balancers
- /health/live: Liveness probe (process alive)
- /health/ready: Readiness probe (dependencies healthy)
"""

import os
import sqlite3
import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from frontend.core.config import settings

# Router for /api/v1 prefix (backward compatibility)
router = APIRouter()

# Router for root-level health endpoints
root_router = APIRouter()


def _check_database() -> bool:
    """Check SQLite database connectivity."""
    try:
        if os.path.exists(settings.DB_PATH):
            con = sqlite3.connect(settings.DB_PATH, timeout=5)
            con.execute("SELECT 1")
            con.close()
            return True
        else:
            # DB file doesn't exist yet, but that's OK for fresh installs
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


# --- /api/v1 endpoints (backward compatibility) ---

@router.get("/health")
async def health_api():
    """
    Health Check endpoint (backward compatible).
    Returns status of all critical dependencies.
    """
    checks = {
        "app": True,
        "database": _check_database(),
        "crawler": _check_crawler(),
    }

    all_healthy = all(checks.values())

    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={
            "ok": all_healthy,
            "checks": checks,
        },
    )


@router.get("/health/live")
async def liveness_api():
    """Kubernetes liveness probe - is the process running? (backward compatible)"""
    return {"ok": True}


@router.get("/health/ready")
async def readiness_api():
    """Kubernetes readiness probe - is the service ready to accept traffic? (backward compatible)"""
    result = await health_api()
    return result
