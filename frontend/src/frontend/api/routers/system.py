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
from shared.postgres.search import get_connection

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


async def _check_crawler() -> bool:
    """Check Crawler service connectivity (non-blocking)."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.CRAWLER_SERVICE_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False


def _check_opensearch() -> dict:
    """Check OpenSearch connectivity and document count."""
    if not settings.OPENSEARCH_ENABLED:
        return {"status": "disabled"}
    try:
        from shared.opensearch.client import INDEX_NAME, get_client

        client = get_client(settings.OPENSEARCH_URL)
        count = client.count(index=INDEX_NAME)["count"]
        return {"status": "ok", "documents": count}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _get_readiness_response():
    """Get readiness status with dependency checks.

    Only database health determines readiness (200 vs 503).
    Crawler status is informational — reported but not gating.
    """
    db_ok = _check_database()
    crawler_ok = await _check_crawler()
    opensearch = _check_opensearch()

    from frontend.services.embedding import _embedding_service

    checks = {
        "database": "ok" if db_ok else "unhealthy",
        "crawler": "ok" if crawler_ok else "degraded",
        "opensearch": opensearch,
        "embeddings": "ok" if _embedding_service else "disabled",
    }

    status = "ok" if db_ok else "unhealthy"

    return JSONResponse(
        status_code=200 if db_ok else 503,
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
    return await _get_readiness_response()


# Kubernetes-style short aliases
@root_router.get("/healthz")
async def healthz():
    """Liveness probe alias (/healthz)."""
    return {"ok": True}


@root_router.get("/readyz")
async def readyz():
    """Readiness probe alias (/readyz)."""
    return await _get_readiness_response()
