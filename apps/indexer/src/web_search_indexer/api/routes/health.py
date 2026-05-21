"""
Health Check Router

Provides canonical health check endpoints:
- /health: Simple health for load balancers
- /readyz: Readiness probe (dependencies healthy)
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from web_search_postgres import ensure_db

root_router = APIRouter()


@root_router.get("/health")
async def health():
    """Simple health check for load balancers."""
    return {"status": "ok"}


@root_router.get("/readyz")
async def readyz():
    """Readiness probe for dependency health."""
    checks = {}
    try:
        ensure_db()
        checks["database"] = True
    except Exception:
        checks["database"] = False

    all_ok = all(checks.values())
    return JSONResponse(
        {"status": "ok" if all_ok else "degraded", "checks": checks},
        status_code=200 if all_ok else 503,
    )
