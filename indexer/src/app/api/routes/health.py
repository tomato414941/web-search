"""
Health Check Router

Provides Kubernetes-compatible health check endpoints:
- /health: Simple health for load balancers
- /health/live: Liveness probe (process alive)
- /health/ready: Readiness probe (dependencies healthy)
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings
from shared.db.search import get_connection

# Router for /api/v1 prefix (backward compatibility)
router = APIRouter()

# Router for root-level health endpoints
root_router = APIRouter()


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
    checks = {}
    try:
        with get_connection(settings.DB_PATH) as conn:
            conn.execute("SELECT 1")
        checks["database"] = True
    except Exception:
        checks["database"] = False

    all_ok = all(checks.values())
    return JSONResponse(
        {"status": "ok" if all_ok else "degraded", "checks": checks},
        status_code=200 if all_ok else 503,
    )


# --- /api/v1 endpoints (backward compatibility) ---


@router.get("/health")
async def health_check() -> dict:
    """Public health check endpoint for load balancer (backward compatible)."""
    return {"status": "ok", "service": "indexer"}
