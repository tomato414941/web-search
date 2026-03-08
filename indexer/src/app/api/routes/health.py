"""
Health Check Router

Provides canonical health check endpoints:
- /health: Simple health for load balancers
- /readyz: Readiness probe (dependencies healthy)
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings
from shared.postgres.search import get_connection

# Router for root-level health endpoints
root_router = APIRouter()


# --- Root-level endpoints ---


@root_router.get("/health")
async def health():
    """Simple health check for load balancers."""
    return {"status": "ok"}


@root_router.get("/readyz")
async def readyz():
    """Readiness probe for dependency health."""
    checks = {}
    try:
        conn = get_connection(settings.DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        checks["database"] = True
    except Exception:
        checks["database"] = False

    all_ok = all(checks.values())
    return JSONResponse(
        {"status": "ok" if all_ok else "degraded", "checks": checks},
        status_code=200 if all_ok else 503,
    )
