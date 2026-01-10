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
from frontend.core.db import ensure_db
from frontend.api.routers import search, search_api, stats, crawler, system, admin
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
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:;"
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
app = FastAPI(
    lifespan=lifespan,
    title="Web Search API",
    version="1.0.0",
    description="A custom full-text search engine with hybrid ranking (BM25 + PageRank + Semantic).",
    openapi_tags=[
        {"name": "search", "description": "Search and discovery endpoints"},
        {"name": "system", "description": "Health checks and system info"},
        {"name": "crawler", "description": "URL submission and crawl control"},
        {"name": "metrics", "description": "Prometheus metrics"},
        {"name": "ui", "description": "Web UI endpoints"},
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
allowed_hosts = os.getenv(
    "ALLOWED_HOSTS", "localhost,127.0.0.1,testclient,testserver"
).split(",")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

# --- CORS ---
cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
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
static_dir = settings.BASE_DIR / "src" / "web_search" / "static"
if not os.path.exists(static_dir):
    static_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static"
    )

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include Routers
# UI routes (no /api/v1 prefix)
app.include_router(search.router, tags=["ui"])
app.include_router(admin.router)

# API routes with /api/v1 prefix
app.include_router(system.router, prefix="/api/v1", tags=["system"])
app.include_router(search_api.router, prefix="/api/v1", tags=["search"])
app.include_router(stats.router, prefix="/api/v1", tags=["system"])
app.include_router(crawler.router, prefix="/api/v1", tags=["crawler"])
app.include_router(metrics_router, prefix="/api/v1", tags=["metrics"])


if __name__ == "__main__":
    uvicorn.run(
        "frontend.api.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
