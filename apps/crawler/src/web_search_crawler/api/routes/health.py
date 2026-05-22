"""
Health Check Router

Provides canonical health check endpoints:
- /health: Simple health for load balancers
- /readyz: Readiness probe (dependencies healthy)
"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from web_search_crawler.db.connection import db_connection
from web_search_crawler.db.executor import run_in_db_executor
from web_search_crawler.core.config import settings

logger = logging.getLogger(__name__)

# Router for root-level health endpoints
root_router = APIRouter()


def _ping_db() -> None:
    with db_connection(settings.CRAWLER_DB_PATH) as cur:
        cur.execute("SELECT 1")


async def _check_db() -> bool:
    """Check PostgreSQL/SQLite connectivity."""
    try:
        await run_in_db_executor(_ping_db)
        return True
    except Exception:
        return False


# --- Root-level endpoints ---


@root_router.get("/health")
async def health():
    """Simple health check for load balancers."""
    return {"status": "ok"}


@root_router.get("/readyz")
async def readyz():
    """Readiness probe for dependency health."""
    checks = {
        "database": "ok" if await _check_db() else "unhealthy",
    }

    all_healthy = all(v == "ok" for v in checks.values())
    status = "ok" if all_healthy else "unhealthy"

    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={"status": status, "checks": checks},
    )
