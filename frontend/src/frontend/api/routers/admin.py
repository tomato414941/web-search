"""Admin Dashboard Router with Authentication."""

import logging
import secrets
from datetime import timedelta
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from pydantic import BaseModel, HttpUrl

from frontend.core.config import settings
from frontend.core.db import get_connection
from frontend.api.templates import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# Session configuration
SESSION_MAX_AGE_SECONDS = int(timedelta(hours=24).total_seconds())
SESSION_COOKIE_NAME = "admin_session"
CSRF_COOKIE_NAME = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"

# Serializer for secure session tokens
_serializer = URLSafeTimedSerializer(settings.SECRET_KEY)


class SeedUrlRequest(BaseModel):
    """Request model for adding seed URLs."""

    url: HttpUrl


def create_session() -> str:
    """Create a new session token using itsdangerous."""
    data = {"user": settings.ADMIN_USERNAME}
    return _serializer.dumps(data)


def validate_session(token: str | None) -> bool:
    """Validate a session token with expiration check."""
    if not token:
        return False
    try:
        _serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return True
    except (BadSignature, SignatureExpired):
        return False


def generate_csrf_token() -> str:
    """Generate a new CSRF token."""
    return secrets.token_urlsafe(32)


def get_csrf_token(request: Request) -> str:
    """Get CSRF token from cookie or generate new one."""
    token = request.cookies.get(CSRF_COOKIE_NAME)
    if not token:
        token = generate_csrf_token()
    return token


def validate_csrf_token(request: Request, form_token: str | None) -> bool:
    """Validate CSRF token from form against cookie."""
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if not cookie_token or not form_token:
        return False
    return secrets.compare_digest(cookie_token, form_token)


def require_auth(request: Request) -> None:
    """Dependency to require authentication."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        raise HTTPException(status_code=401, detail="Unauthorized")


def get_dashboard_data() -> dict[str, Any]:
    """Get comprehensive data for dashboard."""
    data: dict[str, Any] = {
        # Basic stats
        "indexed_pages": 0,
        "indexed_delta": 0,
        "queue_size": 0,
        "visited_count": 0,
        "last_crawl": None,
        # Crawler details
        "worker_status": "unknown",
        "uptime_seconds": None,
        "active_tasks": 0,
        "recent_error_count": 0,
        "crawl_rate": 0,
        # Search stats (today)
        "today_searches": 0,
        "today_unique_queries": 0,
        "today_zero_hits": 0,
        "zero_hit_rate": 0.0,
        "top_query": None,
        # Attention items
        "zero_hit_queries": [],
        "recent_errors": [],
        # Health status
        "health": {"level": "ok", "messages": []},
    }

    # Database stats
    try:
        conn = get_connection(settings.DB_PATH)
        cursor = conn.cursor()
        # Total indexed pages
        cursor.execute("SELECT COUNT(*) FROM documents")
        data["indexed_pages"] = cursor.fetchone()[0]

        # Pages indexed in last 24 hours
        cursor.execute(
            "SELECT COUNT(*) FROM documents "
            "WHERE indexed_at >= NOW() - INTERVAL '1 day'"
        )
        data["indexed_delta"] = cursor.fetchone()[0]

        # Last crawl time
        cursor.execute(
            "SELECT MAX(indexed_at) FROM documents WHERE indexed_at IS NOT NULL"
        )
        result = cursor.fetchone()
        if result and result[0]:
            data["last_crawl"] = result[0]

        # Today's search stats
        cursor.execute(
            """
            SELECT
                COUNT(*) as total,
                COUNT(DISTINCT query) as unique_queries,
                SUM(CASE WHEN result_count = 0 THEN 1 ELSE 0 END) as zero_hits
            FROM search_logs
            WHERE created_at >= CURRENT_DATE
            """
        )
        row = cursor.fetchone()
        if row:
            data["today_searches"] = row[0] or 0
            data["today_unique_queries"] = row[1] or 0
            data["today_zero_hits"] = row[2] or 0
            if data["today_searches"] > 0:
                data["zero_hit_rate"] = round(
                    data["today_zero_hits"] / data["today_searches"] * 100, 1
                )

        # Top query today
        cursor.execute(
            """
            SELECT query, COUNT(*) as count
            FROM search_logs
            WHERE created_at >= CURRENT_DATE
            GROUP BY query
            ORDER BY count DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if row and row[0]:
            data["top_query"] = {"query": row[0], "count": row[1]}

        # Zero-hit queries (top 5)
        cursor.execute(
            """
            SELECT query, COUNT(*) as count
            FROM search_logs
            WHERE result_count = 0 AND created_at >= CURRENT_DATE
            GROUP BY query
            ORDER BY count DESC
            LIMIT 5
            """
        )
        data["zero_hit_queries"] = [
            {"query": row[0], "count": row[1]} for row in cursor.fetchall()
        ]
        cursor.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to get DB stats: {e}")

    # Crawler Stats (Remote)
    crawler_reachable = False
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{settings.CRAWLER_SERVICE_URL}/api/v1/status")
            if resp.status_code == 200:
                crawler_reachable = True
                remote_stats = resp.json()
                data["queue_size"] = remote_stats.get("queue_size", 0)
                data["visited_count"] = remote_stats.get("total_crawled", 0)

            # Worker status
            resp = client.get(f"{settings.CRAWLER_SERVICE_URL}/api/v1/worker/status")
            if resp.status_code == 200:
                worker_data = resp.json()
                data["worker_status"] = worker_data.get("status", "unknown")
                data["uptime_seconds"] = worker_data.get("uptime_seconds")
                data["active_tasks"] = worker_data.get("active_tasks", 0)

            # Recent errors from history
            resp = client.get(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/history?limit=100"
            )
            if resp.status_code == 200:
                history = resp.json()
                # Count errors in last hour and get recent error details
                errors = [h for h in history if h.get("status") == "error"]
                data["recent_error_count"] = len(errors)
                data["recent_errors"] = [
                    {
                        "url": e.get("url", ""),
                        "error_message": e.get("error_message", "Unknown"),
                    }
                    for e in errors[:5]
                ]
                # Calculate crawl rate (pages/hour based on recent history)
                if history:
                    data["crawl_rate"] = len(history)  # Approximation
    except Exception as e:
        logger.warning(f"Failed to get crawler stats: {e}")

    # Determine health status
    health_messages = []
    if not crawler_reachable:
        health_messages.append("Crawler service is unreachable")
        data["health"]["level"] = "error"
    elif data["worker_status"] == "stopped":
        health_messages.append("Crawler is stopped. Indexing paused.")
        data["health"]["level"] = "warning"
    elif data["queue_size"] == 0 and data["worker_status"] == "running":
        health_messages.append("Queue is empty. Waiting for new URLs.")
        data["health"]["level"] = "warning"

    if data["zero_hit_rate"] > 50 and data["today_searches"] >= 10:
        health_messages.append(
            f"High zero-hit rate: {data['zero_hit_rate']}% of searches returned no results"
        )
        if data["health"]["level"] == "ok":
            data["health"]["level"] = "warning"

    data["health"]["messages"] = health_messages

    return data


# ==================== Routes ====================


def _add_csrf_cookie(response: RedirectResponse, token: str) -> RedirectResponse:
    """Add CSRF token cookie to response."""
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=False,  # JS needs access for AJAX requests
        samesite="strict",
    )
    return response


@router.get("/login")
async def login_page(request: Request, error: str = ""):
    """Login page."""
    csrf_token = get_csrf_token(request)
    response = templates.TemplateResponse(
        "admin/login.html",
        {"request": request, "error": error, "csrf_token": csrf_token},
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=False,
        samesite="strict",
    )
    return response


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    """Process login."""
    # Validate CSRF token
    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(
            url="/admin/login?error=Invalid+request", status_code=303
        )

    if username == settings.ADMIN_USERNAME and password == settings.ADMIN_PASSWORD:
        token = create_session()
        new_csrf = generate_csrf_token()
        response = RedirectResponse(url="/admin/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE_NAME,
            token,
            max_age=SESSION_MAX_AGE_SECONDS,
            httponly=True,
            samesite="strict",
        )
        _add_csrf_cookie(response, new_csrf)
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

    data = get_dashboard_data()
    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "data": data,
            "crawler_url": settings.CRAWLER_SERVICE_URL,
            "csrf_token": csrf_token,
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
    except httpx.RequestError as e:
        logger.warning(f"Failed to fetch seeds from crawler: {e}")
        seeds = []

    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        "admin/seeds.html",
        {
            "request": request,
            "seeds": seeds,
            "success": success,
            "error": error,
            "csrf_token": csrf_token,
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
    except httpx.RequestError as e:
        logger.warning(f"Failed to fetch queue from crawler: {e}")
        queue_urls = []

    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        "admin/queue.html",
        {
            "request": request,
            "queue_urls": queue_urls,
            "success": success,
            "error": error,
            "csrf_token": csrf_token,
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
    except httpx.RequestError as e:
        logger.warning(f"Failed to fetch history from crawler: {e}")

    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        "admin/history.html",
        {
            "request": request,
            "history_logs": history_logs,
            "url_filter": url,
            "csrf_token": csrf_token,
        },
    )


@router.post("/seeds")
async def add_seed(
    request: Request,
    url: str = Form(...),
    priority: float = Form(default=100.0),
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    """Add a seed URL (persistent)."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(
            url="/admin/seeds?error=Invalid+request", status_code=303
        )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            payload = {"urls": [url], "priority": priority}
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/seeds", json=payload
            )
            if resp.status_code != 200:
                raise Exception(f"Crawler API Error: {resp.text}")

        return RedirectResponse(
            url=f"/admin/seeds?success={quote(f'Added seed {url}', safe='')}",
            status_code=303,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/admin/seeds?error={quote(str(e), safe='')}",
            status_code=303,
        )


@router.post("/seeds/delete")
async def delete_seed(
    request: Request,
    url: str = Form(...),
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    """Delete a seed URL."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(
            url="/admin/seeds?error=Invalid+request", status_code=303
        )

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
            url=f"/admin/seeds?success={quote('Seed deleted', safe='')}",
            status_code=303,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/admin/seeds?error={quote(str(e), safe='')}",
            status_code=303,
        )


@router.post("/seeds/requeue")
async def requeue_seeds(
    request: Request,
    force: bool = Form(default=False),
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    """Requeue all seeds."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(
            url="/admin/seeds?error=Invalid+request", status_code=303
        )

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
            url=f"/admin/seeds?success={quote(f'Requeued {count} seeds', safe='')}",
            status_code=303,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/admin/seeds?error={quote(str(e), safe='')}",
            status_code=303,
        )


@router.post("/queue")
async def add_to_queue(
    request: Request,
    url: str = Form(...),
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    """Add a URL to the queue (temporary, not a seed)."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(
            url="/admin/queue?error=Invalid+request", status_code=303
        )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            payload = {"urls": [url], "priority": 100}
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/urls", json=payload
            )
            if resp.status_code != 200:
                raise Exception(f"Crawler API Error: {resp.text}")

        return RedirectResponse(
            url=f"/admin/queue?success={quote(f'Added {url} to queue', safe='')}",
            status_code=303,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/admin/queue?error={quote(str(e), safe='')}",
            status_code=303,
        )


@router.post("/crawler/start")
async def crawler_start(
    request: Request,
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    """Start the crawler worker."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(url="/admin/", status_code=303)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/worker/start"
            )
            if resp.status_code != 200:
                logger.warning(f"Failed to start crawler: {resp.text}")
    except httpx.RequestError as e:
        logger.warning(f"Failed to start crawler: {e}")

    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/crawler/stop")
async def crawler_stop(
    request: Request,
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    """Stop the crawler worker (graceful)."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(url="/admin/", status_code=303)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/worker/stop",
                json={},
            )
            if resp.status_code != 200:
                logger.warning(f"Failed to stop crawler: {resp.text}")
    except httpx.RequestError as e:
        logger.warning(f"Failed to stop crawler: {e}")

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
        cursor = conn.cursor()
        # Total searches in last 7 days
        cursor.execute(
            """
            SELECT COUNT(*) FROM search_logs
            WHERE created_at >= NOW() - INTERVAL '7 days'
            """
        )
        data["total_searches"] = cursor.fetchone()[0]

        # Top queries (last 7 days)
        cursor.execute(
            """
            SELECT query, COUNT(*) as count, AVG(result_count) as avg_results
            FROM search_logs
            WHERE created_at >= NOW() - INTERVAL '7 days'
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
        cursor.execute(
            """
            SELECT query, COUNT(*) as count
            FROM search_logs
            WHERE result_count = 0 AND created_at >= NOW() - INTERVAL '7 days'
            GROUP BY query
            ORDER BY count DESC
            LIMIT 20
            """
        )
        data["zero_hit_queries"] = [
            {"query": row[0], "count": row[1]} for row in cursor.fetchall()
        ]
        cursor.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to get analytics data: {e}")

    return data


@router.get("/analytics")
async def analytics_page(request: Request):
    """Search analytics page."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    analytics = get_analytics_data()
    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        "admin/analytics.html",
        {
            "request": request,
            "analytics": analytics,
            "csrf_token": csrf_token,
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
                status["state"] = worker.get("status", "unknown")
                status["uptime"] = worker.get("uptime")
                status["concurrency"] = worker.get("concurrency")
    except httpx.RequestError as e:
        logger.debug(f"Crawler instance {url} unreachable: {e}")
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
    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        "admin/crawlers.html",
        {
            "request": request,
            "instances": instances,
            "csrf_token": csrf_token,
        },
    )


@router.post("/crawlers/{name}/start")
async def crawler_instance_start(
    request: Request,
    name: str,
    concurrency: int = Form(default=1),
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    """Start a specific crawler instance."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(url="/admin/crawlers", status_code=303)

    url = find_crawler_url(name)
    if not url:
        return RedirectResponse(url="/admin/crawlers", status_code=303)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{url}/api/v1/worker/start", json={"concurrency": concurrency}
            )
    except httpx.RequestError as e:
        logger.warning(f"Failed to start crawler instance {name}: {e}")

    return RedirectResponse(url="/admin/crawlers", status_code=303)


@router.post("/crawlers/{name}/stop")
async def crawler_instance_stop(
    request: Request,
    name: str,
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    """Stop a specific crawler instance."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(url="/admin/crawlers", status_code=303)

    url = find_crawler_url(name)
    if not url:
        return RedirectResponse(url="/admin/crawlers", status_code=303)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{url}/api/v1/worker/stop", json={})
    except httpx.RequestError as e:
        logger.warning(f"Failed to stop crawler instance {name}: {e}")

    return RedirectResponse(url="/admin/crawlers", status_code=303)
