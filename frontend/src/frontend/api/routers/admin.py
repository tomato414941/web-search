"""Admin Dashboard Router with Authentication."""

import hashlib
import hmac
import sqlite3
from datetime import timedelta
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl

from frontend.core.config import settings
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
    }

    # Database stats (Local SQLite)
    try:
        if settings.DB_PATH:
            conn = sqlite3.connect(settings.DB_PATH)
            cursor = conn.execute("SELECT COUNT(*) FROM pages")
            stats["indexed_pages"] = cursor.fetchone()[0]

            cursor = conn.execute(
                "SELECT MAX(indexed_at) FROM pages WHERE indexed_at IS NOT NULL"
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
            resp = client.get(f"{settings.CRAWLER_SERVICE_URL}/status")
            if resp.status_code == 200:
                remote_stats = resp.json()
                stats["queue_size"] = remote_stats.get("queued", 0)
                stats["visited_count"] = remote_stats.get("visited", 0)
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

    # Get current queue contents from Crawler API
    queue_urls = []
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.CRAWLER_SERVICE_URL}/queue?limit=20")
            if resp.status_code == 200:
                items = resp.json()
                queue_urls = [(item["url"], item["score"]) for item in items]
    except Exception:
        queue_urls = []

    return templates.TemplateResponse(
        "admin/seeds.html",
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
                f"{settings.CRAWLER_SERVICE_URL}/history", params=params
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
async def add_seed(request: Request, url: str = Form(...)):
    """Add a seed URL to the queue."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            payload = {"urls": [url], "priority": 100}
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/crawl", json=payload
            )
            if resp.status_code != 200:
                raise Exception(f"Crawler API Error: {resp.text}")

        return RedirectResponse(
            url=f"/admin/seeds?success=Added+{url}+to+queue",
            status_code=303,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/admin/seeds?error={str(e)}",
            status_code=303,
        )
