import os
import sqlite3
import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from frontend.core.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    """
    Health Check endpoint.
    Returns status of all critical dependencies.
    """
    checks = {
        "app": True,
        "database": False,
        "crawler": False,
    }

    # Check SQLite database
    try:
        if os.path.exists(settings.DB_PATH):
            con = sqlite3.connect(settings.DB_PATH, timeout=5)
            con.execute("SELECT 1")
            con.close()
            checks["database"] = True
        else:
            # DB file doesn't exist yet, but that's OK for fresh installs
            checks["database"] = True
    except Exception:
        checks["database"] = False
    # Check Crawler Service
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{settings.CRAWLER_SERVICE_URL}/health")
            if resp.status_code == 200:
                checks["crawler"] = True
            else:
                checks["crawler"] = False
    except Exception:
        checks["crawler"] = False

    # Overall health
    all_healthy = all(checks.values())

    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={
            "ok": all_healthy,
            "checks": checks,
        },
    )


@router.get("/health/live")
async def liveness():
    """Kubernetes liveness probe - is the process running?"""
    return {"ok": True}


@router.get("/health/ready")
async def readiness():
    """Kubernetes readiness probe - is the service ready to accept traffic?"""
    # Reuse the main health check
    result = await health()
    return result
