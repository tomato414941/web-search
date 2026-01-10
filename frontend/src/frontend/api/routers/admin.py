"""Admin Dashboard Router with Authentication."""

import hashlib
import hmac
import sqlite3
from datetime import timedelta
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, HttpUrl

from shared.core.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])

# Redis-based session storage (works with multiple workers)
SESSION_DURATION = timedelta(hours=24)
SESSION_COOKIE_NAME = "admin_session"
SESSION_PREFIX = "admin:session:"


class SeedUrlRequest(BaseModel):
    """Request model for adding seed URLs."""

    url: HttpUrl


# ...


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
    # Constant time comparison
    return hmac.compare_digest(token, get_session_hash())


def require_auth(request: Request) -> None:
    """Dependency to require authentication."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        raise HTTPException(status_code=401, detail="Unauthorized")


# ... imports ...


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

            # Get last indexed time
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
        # Call Crawler API
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{settings.CRAWLER_SERVICE_URL}/status")
            if resp.status_code == 200:
                remote_stats = resp.json()
                stats["queue_size"] = remote_stats.get("queued", 0)
                stats["visited_count"] = remote_stats.get("visited", 0)
    except Exception as e:
        # If crawler is down, just show 0
        print(f"Crawler stats error: {e}")
        pass

    return stats


def get_recent_searches() -> list[dict]:
    """Get recent search queries (placeholder - needs search logging)."""
    # TODO: Implement search logging
    return []


# ==================== HTML Templates ====================


def admin_base_template(content: str, title: str = "Admin") -> str:
    """Base HTML template for admin pages."""
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Pale Blue Search Admin</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{
            display: flex; justify-content: space-between; align-items: center;
            padding: 20px 0; border-bottom: 1px solid #333;
            margin-bottom: 30px;
        }}
        .header h1 {{ color: #64b5f6; font-size: 1.5rem; }}
        .header a {{ color: #999; text-decoration: none; }}
        .header a:hover {{ color: #fff; }}
        .nav {{ display: flex; gap: 20px; }}
        .nav a {{
            color: #64b5f6; text-decoration: none; padding: 8px 16px;
            border-radius: 4px; transition: background 0.2s;
        }}
        .nav a:hover {{ background: rgba(100, 181, 246, 0.1); }}
        .nav a.active {{ background: rgba(100, 181, 246, 0.2); }}
        .card {{
            background: rgba(255, 255, 255, 0.05);
            border-radius: 12px; padding: 24px;
            margin-bottom: 20px; border: 1px solid #333;
        }}
        .card h2 {{ color: #64b5f6; margin-bottom: 16px; font-size: 1.2rem; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }}
        .stat-box {{
            background: rgba(100, 181, 246, 0.1);
            padding: 20px; border-radius: 8px; text-align: center;
        }}
        .stat-box .value {{ font-size: 2rem; font-weight: bold; color: #64b5f6; }}
        .stat-box .label {{ color: #999; margin-top: 4px; }}
        input, button {{
            padding: 12px 16px; border-radius: 6px; border: 1px solid #444;
            background: #2a2a3e; color: #fff; font-size: 1rem;
        }}
        input:focus {{ outline: none; border-color: #64b5f6; }}
        button {{
            background: #64b5f6; color: #1a1a2e; border: none; cursor: pointer;
            font-weight: 600; transition: background 0.2s;
        }}
        button:hover {{ background: #90caf9; }}
        button.danger {{ background: #ef5350; }}
        button.danger:hover {{ background: #f44336; }}
        .form-row {{ display: flex; gap: 12px; margin-bottom: 16px; }}
        .form-row input {{ flex: 1; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #333; }}
        th {{ color: #64b5f6; }}
        .login-box {{
            max-width: 400px; margin: 100px auto;
            background: rgba(255, 255, 255, 0.05);
            padding: 40px; border-radius: 12px; border: 1px solid #333;
        }}
        .login-box h1 {{ text-align: center; margin-bottom: 30px; color: #64b5f6; }}
        .login-box input {{ width: 100%; margin-bottom: 16px; }}
        .login-box button {{ width: 100%; }}
        .error {{ color: #ef5350; margin-bottom: 16px; }}
        .success {{ color: #66bb6a; margin-bottom: 16px; }}
    </style>
</head>
<body>
    {content}
</body>
</html>
"""


# ==================== Routes ====================


@router.get("/login", response_class=HTMLResponse)
async def login_page(error: str = ""):
    """Login page."""
    error_html = f'<p class="error">{error}</p>' if error else ""
    content = f"""
    <div class="login-box">
        <h1>🔍 Admin Login</h1>
        {error_html}
        <form method="post" action="/admin/login">
            <input type="text" name="username" placeholder="Username" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
    </div>
    """
    return admin_base_template(content, "Login")


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


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    stats = get_stats()
    content = f"""
    <div class="container">
        <div class="header">
            <h1>🔍 Pale Blue Search Admin</h1>
            <div class="nav">
                <a href="/admin/" class="active">Dashboard</a>
                <a href="/admin/seeds">Seed URLs</a>
                <a href="/admin/logout">Logout</a>
            </div>
        </div>

        <div class="card">
            <h2>📊 Statistics</h2>
            <div class="stats-grid">
                <div class="stat-box">
                    <div class="value">{stats["indexed_pages"]:,}</div>
                    <div class="label">Indexed Pages</div>
                </div>
                <div class="stat-box">
                    <div class="value">{stats["queue_size"]:,}</div>
                    <div class="label">Queue Size</div>
                </div>
                <div class="stat-box">
                    <div class="value">{stats["visited_count"]:,}</div>
                    <div class="label">Visited URLs</div>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>⚙️ System Status</h2>
            <table>
                <tr><th>Last Crawl</th><td>{stats["last_crawl"] or "Never"}</td></tr>
                <tr><th>Crawler API</th><td>{settings.CRAWLER_SERVICE_URL}</td></tr>
            </table>
        </div>

        <div class="card">
            <h2>🔗 Quick Actions</h2>
            <div class="form-row">
                <a href="/admin/seeds"><button>Manage Seed URLs</button></a>
                <a href="/"><button>View Search</button></a>
                <a href="/api/stats"><button>API Stats</button></a>
            </div>
        </div>
    </div>
    """
    return admin_base_template(content, "Dashboard")


@router.get("/seeds", response_class=HTMLResponse)
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
                # Expecting list of {"url": "...", "score": 100.0}
                items = resp.json()
                queue_urls = [(item["url"], item["score"]) for item in items]
    except Exception:
        queue_urls = []  # Fail gracefully

    urls_html = ""
    for url, score in queue_urls:
        urls_html += f"<tr><td>{url}</td><td>{score:.2f}</td></tr>"

    if not urls_html:
        urls_html = (
            "<tr><td colspan='2'>Queue is empty or Crawler unavailable</td></tr>"
        )

    success_html = f'<p class="success">{success}</p>' if success else ""
    error_html = f'<p class="error">{error}</p>' if error else ""

    content = f"""
    <div class="container">
        <div class="header">
            <h1>🔍 Pale Blue Search Admin</h1>
            <div class="nav">
                <a href="/admin/">Dashboard</a>
                <a href="/admin/seeds" class="active">Seed URLs</a>
                <a href="/admin/logout">Logout</a>
            </div>
        </div>

        <div class="card">
            <h2>➕ Add Seed URL</h2>
            {success_html}{error_html}
            <form method="post" action="/admin/seeds" class="form-row">
                <input type="url" name="url" placeholder="https://example.com" required>
                <button type="submit">Add to Queue</button>
            </form>
        </div>

        <div class="card">
            <h2>📋 Current Queue (Top 20)</h2>
            <table>
                <thead><tr><th>URL</th><th>Score</th></tr></thead>
                <tbody>{urls_html}</tbody>
            </table>
        </div>
    </div>
    """
    return admin_base_template(content, "Seed URLs")


@router.get("/history", response_class=HTMLResponse)
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

    history_html = ""
    for log in history_logs:
        status_color = "#66bb6a" if log["status"] == "indexed" else "#ef5350"
        if log["status"] == "blocked":
            status_color = "#ffa726"

        history_html += f"""
        <tr>
            <td>{log["created_at"]}</td>
            <td><span style="color: {status_color}">{log["status"]}</span></td>
            <td>{log["http_code"] or "-"}</td>
            <td>{log["url"]}</td>
            <td>{log["error_message"] or ""}</td>
        </tr>
        """

    if not history_html:
        history_html = "<tr><td colspan='5'>No logs found</td></tr>"

    content = f"""
    <div class="container">
        <div class="header">
            <h1>🔍 Pale Blue Search Admin</h1>
            <div class="nav">
                <a href="/admin/">Dashboard</a>
                <a href="/admin/seeds">Seed URLs</a>
                <a href="/admin/history" class="active">History</a>
                <a href="/admin/logout">Logout</a>
            </div>
        </div>

        <div class="card">
            <h2>📜 Crawl History</h2>
            <form method="get" action="/admin/history" class="form-row">
                <input type="text" name="url" placeholder="Filter by URL..." value="{url}">
                <button type="submit">Filter</button>
            </form>

            <table>
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Status</th>
                        <th>Code</th>
                        <th>URL</th>
                        <th>Message</th>
                    </tr>
                </thead>
                <tbody>{history_html}</tbody>
            </table>
        </div>
    </div>
    """
    return admin_base_template(content, "Crawl History")


@router.post("/seeds")
async def add_seed(request: Request, url: str = Form(...)):
    """Add a seed URL to the queue."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not validate_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        # Send to Crawler API
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
