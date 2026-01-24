"""Admin Dashboard Router with Authentication."""

import hashlib
import hmac
from datetime import timedelta
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl

from frontend.core.config import settings
from frontend.core.db import get_connection
from frontend.api.templates import templates

router = APIRouter(prefix="/admin", tags=["admin"])

# Session configuration
SESSION_DURATION = timedelta(hours=24)
SESSION_COOKIE_NAME = "admin_session"


class SeedUrlRequest(BaseModel):
    """Request model for adding seed URLs."""

    url: HttpUrl


def get_session_hash() -> str:
    """Generate expected session hash."""
    msg = f"{settings.ADMIN_USERNAME}:{settings.ADMIN_PASSWORD}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def create_session() -> str:
    """Create a new session token (HMAC of creds)."""
    return get_session_hash()


def validate_session(token: str | None) -> bool:
    """Validate a session token."""
    if not token:
        return False
    return hmac.compare_digest(token, get_session_hash())


def require_auth(request: Request) -> None:
    """Dependency to require authentication."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        raise HTTPException(status_code=401, detail="Unauthorized")


def get_stats() -> dict[str, Any]:
    """Get comprehensive stats for dashboard."""
    stats = {
        "indexed_pages": 0,
        "queue_size": 0,
        "visited_count": 0,
        "last_crawl": None,
        "worker_status": "unknown",
    }

    # Database stats (Local SQLite)
    try:
        if settings.DB_PATH:
            conn = get_connection(settings.DB_PATH)
            cursor = conn.execute("SELECT COUNT(*) FROM documents")
            stats["indexed_pages"] = cursor.fetchone()[0]

            cursor = conn.execute(
                "SELECT MAX(indexed_at) FROM documents WHERE indexed_at IS NOT NULL"
            )
            result = cursor.fetchone()
            if result and result[0]:
                stats["last_crawl"] = result[0]
            conn.close()
    except Exception:
        pass

    # Crawler Stats (Remote)
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{settings.CRAWLER_SERVICE_URL}/api/v1/status")
            if resp.status_code == 200:
                remote_stats = resp.json()
                stats["queue_size"] = remote_stats.get("queue_size", 0)
                stats["visited_count"] = remote_stats.get("total_crawled", 0)

            # Get worker status
            resp = client.get(f"{settings.CRAWLER_SERVICE_URL}/api/v1/worker/status")
            if resp.status_code == 200:
                worker_data = resp.json()
                stats["worker_status"] = worker_data.get("state", "unknown")
    except Exception:
        pass

    return stats


# ==================== Routes ====================


@router.get("/login")
async def login_page(request: Request, error: str = ""):
    """Login page."""
    return templates.TemplateResponse(
        "admin/login.html",
        {"request": request, "error": error},
    )


@router.post("/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
):
    """Process login."""
    if username == settings.ADMIN_USERNAME and password == settings.ADMIN_PASSWORD:
        token = create_session()
        response = RedirectResponse(url="/admin/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE_NAME,
            token,
            max_age=int(SESSION_DURATION.total_seconds()),
            httponly=True,
            samesite="strict",
        )
        return response
    return RedirectResponse(
        url="/admin/login?error=Invalid+credentials", status_code=303
    )


@router.get("/logout")
async def logout():
    """Logout and clear session."""
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/")
async def dashboard(request: Request):
    """Main dashboard page."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    stats = get_stats()
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "stats": stats,
            "crawler_url": settings.CRAWLER_SERVICE_URL,
        },
    )


@router.get("/seeds")
async def seeds_page(request: Request, success: str = "", error: str = ""):
    """Seed URL management page."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    # Get seeds from Crawler API
    seeds = []
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.CRAWLER_SERVICE_URL}/api/v1/seeds")
            if resp.status_code == 200:
                seeds = resp.json()
    except Exception:
        seeds = []

    return templates.TemplateResponse(
        "admin/seeds.html",
        {
            "request": request,
            "seeds": seeds,
            "success": success,
            "error": error,
        },
    )


@router.get("/queue")
async def queue_page(request: Request, success: str = "", error: str = ""):
    """Crawl queue page."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    # Get current queue contents from Crawler API
    queue_urls = []
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/queue?limit=50"
            )
            if resp.status_code == 200:
                items = resp.json()
                queue_urls = [(item["url"], item["score"]) for item in items]
    except Exception:
        queue_urls = []

    return templates.TemplateResponse(
        "admin/queue.html",
        {
            "request": request,
            "queue_urls": queue_urls,
            "success": success,
            "error": error,
        },
    )


@router.get("/history")
async def history_page(request: Request, url: str = ""):
    """Crawl history page."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    # Fetch history from Crawler
    history_logs = []
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            params = {"url": url} if url else {}
            resp = await client.get(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/history", params=params
            )
            if resp.status_code == 200:
                history_logs = resp.json()
    except Exception:
        pass

    return templates.TemplateResponse(
        "admin/history.html",
        {
            "request": request,
            "history_logs": history_logs,
            "url_filter": url,
        },
    )


@router.post("/seeds")
async def add_seed(
    request: Request, url: str = Form(...), priority: float = Form(default=100.0)
):
    """Add a seed URL (persistent)."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            payload = {"urls": [url], "priority": priority}
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/seeds", json=payload
            )
            if resp.status_code != 200:
                raise Exception(f"Crawler API Error: {resp.text}")

        return RedirectResponse(
            url=f"/admin/seeds?success=Added+seed+{url}",
            status_code=303,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/admin/seeds?error={str(e)}",
            status_code=303,
        )


@router.post("/seeds/delete")
async def delete_seed(request: Request, url: str = Form(...)):
    """Delete a seed URL."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            payload = {"urls": [url]}
            resp = await client.request(
                "DELETE",
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/seeds",
                json=payload,
            )
            if resp.status_code != 200:
                raise Exception(f"Crawler API Error: {resp.text}")

        return RedirectResponse(
            url="/admin/seeds?success=Seed+deleted",
            status_code=303,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/admin/seeds?error={str(e)}",
            status_code=303,
        )


@router.post("/seeds/requeue")
async def requeue_seeds(request: Request, force: bool = Form(default=False)):
    """Requeue all seeds."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            payload = {"force": force}
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/seeds/requeue",
                json=payload,
            )
            if resp.status_code != 200:
                raise Exception(f"Crawler API Error: {resp.text}")
            data = resp.json()
            count = data.get("count", 0)

        return RedirectResponse(
            url=f"/admin/seeds?success=Requeued+{count}+seeds",
            status_code=303,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/admin/seeds?error={str(e)}",
            status_code=303,
        )


@router.post("/queue")
async def add_to_queue(request: Request, url: str = Form(...)):
    """Add a URL to the queue (temporary, not a seed)."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            payload = {"urls": [url], "priority": 100}
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/urls", json=payload
            )
            if resp.status_code != 200:
                raise Exception(f"Crawler API Error: {resp.text}")

        return RedirectResponse(
            url=f"/admin/queue?success=Added+{url}+to+queue",
            status_code=303,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/admin/queue?error={str(e)}",
            status_code=303,
        )


@router.post("/crawler/start")
async def crawler_start(request: Request):
    """Start the crawler worker."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/worker/start"
            )
            if resp.status_code != 200:
                raise Exception(f"Failed to start crawler: {resp.text}")
    except Exception:
        pass  # Redirect back to dashboard regardless

    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/crawler/stop")
async def crawler_stop(request: Request):
    """Stop the crawler worker (graceful)."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/worker/stop"
            )
            if resp.status_code != 200:
                raise Exception(f"Failed to stop crawler: {resp.text}")
    except Exception:
        pass  # Redirect back to dashboard regardless

    return RedirectResponse(url="/admin/", status_code=303)


def get_analytics_data() -> dict:
    """Get search analytics data."""
    data = {
        "top_queries": [],
        "zero_hit_queries": [],
        "total_searches": 0,
    }

    try:
        conn = get_connection(settings.DB_PATH)

        # Total searches in last 7 days
        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM search_logs
            WHERE created_at >= datetime('now', '-7 days')
            """
        )
        data["total_searches"] = cursor.fetchone()[0]

        # Top queries (last 7 days)
        cursor = conn.execute(
            """
            SELECT query, COUNT(*) as count, AVG(result_count) as avg_results
            FROM search_logs
            WHERE created_at >= datetime('now', '-7 days')
            GROUP BY query
            ORDER BY count DESC
            LIMIT 20
            """
        )
        data["top_queries"] = [
            {"query": row[0], "count": row[1], "avg_results": round(row[2], 1)}
            for row in cursor.fetchall()
        ]

        # Zero-hit queries (content gaps)
        cursor = conn.execute(
            """
            SELECT query, COUNT(*) as count
            FROM search_logs
            WHERE result_count = 0 AND created_at >= datetime('now', '-7 days')
            GROUP BY query
            ORDER BY count DESC
            LIMIT 20
            """
        )
        data["zero_hit_queries"] = [
            {"query": row[0], "count": row[1]} for row in cursor.fetchall()
        ]

        conn.close()
    except Exception:
        pass

    return data


@router.get("/analytics")
async def analytics_page(request: Request):
    """Search analytics page."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    analytics = get_analytics_data()
    return templates.TemplateResponse(
        "admin/analytics.html",
        {
            "request": request,
            "analytics": analytics,
        },
    )


# ==================== Crawler Instances Management ====================


async def get_crawler_instance_status(url: str) -> dict[str, Any]:
    """Get status for a single crawler instance."""
    status = {
        "state": "unreachable",
        "queue_size": 0,
        "total_crawled": 0,
        "uptime": None,
        "concurrency": None,
    }
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{url}/api/v1/status")
            if resp.status_code == 200:
                data = resp.json()
                status["queue_size"] = data.get("queue_size", 0)
                status["total_crawled"] = data.get("total_crawled", 0)

            resp = await client.get(f"{url}/api/v1/worker/status")
            if resp.status_code == 200:
                worker = resp.json()
                status["state"] = worker.get("state", "unknown")
                status["uptime"] = worker.get("uptime")
                status["concurrency"] = worker.get("concurrency")
    except Exception:
        pass
    return status


async def get_all_crawler_instances() -> list[dict[str, Any]]:
    """Get status for all configured crawler instances."""
    instances = []
    for inst in settings.CRAWLER_INSTANCES:
        status = await get_crawler_instance_status(inst["url"])
        instances.append(
            {
                "name": inst["name"],
                "url": inst["url"],
                **status,
            }
        )
    return instances


def find_crawler_url(name: str) -> str | None:
    """Find crawler URL by name."""
    for inst in settings.CRAWLER_INSTANCES:
        if inst["name"] == name:
            return inst["url"]
    return None


@router.get("/crawlers")
async def crawlers_page(request: Request):
    """Crawler instances management page."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    instances = await get_all_crawler_instances()
    return templates.TemplateResponse(
        "admin/crawlers.html",
        {
            "request": request,
            "instances": instances,
        },
    )


@router.post("/crawlers/{name}/start")
async def crawler_instance_start(
    request: Request, name: str, concurrency: int = Form(default=1)
):
    """Start a specific crawler instance."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    url = find_crawler_url(name)
    if not url:
        return RedirectResponse(url="/admin/crawlers", status_code=303)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{url}/api/v1/worker/start", json={"concurrency": concurrency}
            )
    except Exception:
        pass

    return RedirectResponse(url="/admin/crawlers", status_code=303)


@router.post("/crawlers/{name}/stop")
async def crawler_instance_stop(request: Request, name: str):
    """Stop a specific crawler instance."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    url = find_crawler_url(name)
    if not url:
        return RedirectResponse(url="/admin/crawlers", status_code=303)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{url}/api/v1/worker/stop")
    except Exception:
        pass

    return RedirectResponse(url="/admin/crawlers", status_code=303)
