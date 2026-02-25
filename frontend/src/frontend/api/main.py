import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi.errors import RateLimitExceeded

from frontend.core.config import settings
from shared.db.search import ensure_db
from frontend.api.routers import search, search_api, stats, crawler, admin, quality
from frontend.api.routers.system import root_router as health_root_router
from frontend.api.middleware.rate_limiter import limiter, rate_limit_exceeded_handler
from frontend.api.middleware.request_logging import RequestLoggingMiddleware
from frontend.api.metrics import router as metrics_router, MetricsMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Content Security Policy (adjust as needed for your assets)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://www.google.com https://*.gstatic.com https://fastapi.tiangolo.com;"
        )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- DB Initialization ---
    db_dir = os.path.dirname(settings.DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    ensure_db(settings.DB_PATH)
    yield


# --- OpenAPI Metadata ---
API_DESCRIPTION = """\
Web search API powered by a custom crawler with BM25 ranking and PageRank boosting.

## Authentication

API keys are **optional**. Anonymous requests work but don't include usage tracking.

| Method | Example |
|---|---|
| Header | `X-API-Key: pbs_...` |
| Query param | `?api_key=pbs_...` |

Request an API key via the [admin dashboard](/admin/).

## Rate Limits

| Scope | Limit |
|---|---|
| IP-based (anonymous) | 100 req/min |
| API key (authenticated) | 1,000 req/day |
"""

app = FastAPI(
    lifespan=lifespan,
    title="PaleBluSearch API",
    version="1.0.0",
    description=API_DESCRIPTION,
    openapi_tags=[
        {"name": "search", "description": "Search and click tracking"},
    ],
    license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
)

# --- Rate Limiter ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# --- Middleware (order matters: last added = first executed) ---
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(MetricsMiddleware)

# Trusted Hosts (prevent Host header attacks)
# 'testclient' and 'testserver' are included for HTTPX/Starlette TestClient compatibility
if settings.DEBUG:
    allowed_hosts = ["*"]
else:
    allowed_hosts = settings.ALLOWED_HOSTS
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

# --- CORS ---
cors_origins_env = os.getenv("CORS_ORIGINS")
if cors_origins_env:
    cors_origins = cors_origins_env.split(",")
else:
    # Public API: allow all origins by default (API key auth via header, not cookies)
    cors_origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# --- Custom Error Handlers ---
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: StarletteHTTPException):
    """Custom 404 page."""
    template_path = os.path.join(
        os.path.dirname(__file__), "..", "templates", "error", "404.html"
    )
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=404)
    return HTMLResponse(content="<h1>404 - Not Found</h1>", status_code=404)


@app.exception_handler(500)
async def server_error_handler(request: Request, exc: Exception):
    """Custom 500 page."""
    template_path = os.path.join(
        os.path.dirname(__file__), "..", "templates", "error", "500.html"
    )
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=500)
    return HTMLResponse(content="<h1>500 - Server Error</h1>", status_code=500)


# Mount Static
static_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static"
)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include Routers
# Root-level health endpoints (Kubernetes probes)
app.include_router(health_root_router, tags=["health"], include_in_schema=False)

# UI routes (no /api/v1 prefix)
app.include_router(search.router, tags=["ui"], include_in_schema=False)
app.include_router(admin.router, include_in_schema=False)

# API routes with /api/v1 prefix
app.include_router(search_api.router, prefix="/api/v1", tags=["search"])
app.include_router(
    stats.router, prefix="/api/v1", tags=["system"], include_in_schema=False
)
app.include_router(
    crawler.router, prefix="/api/v1", tags=["crawler"], include_in_schema=False
)
app.include_router(
    quality.router, prefix="/api/v1", tags=["system"], include_in_schema=False
)
app.include_router(
    metrics_router, prefix="/api/v1", tags=["metrics"], include_in_schema=False
)


if __name__ == "__main__":
    uvicorn.run(
        "frontend.api.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
