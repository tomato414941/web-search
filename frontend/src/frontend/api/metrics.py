# Prometheus Metrics for FastAPI
# Provides /metrics endpoint for scraping

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from fastapi import APIRouter, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time

router = APIRouter()

# --- Metrics Definitions ---

# Request counter (by method, path, status)
REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)

# Request latency histogram
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# Active requests gauge
ACTIVE_REQUESTS = Gauge("http_requests_active", "Number of active HTTP requests")

# Search-specific metrics
SEARCH_COUNT = Counter(
    "search_requests_total",
    "Total search requests",
    ["mode"],  # "default" or "semantic"
)

SEARCH_LATENCY = Histogram(
    "search_duration_seconds",
    "Search request latency",
    ["mode"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect request metrics."""

    async def dispatch(self, request: Request, call_next):
        # Skip metrics endpoint itself
        if request.url.path == "/metrics":
            return await call_next(request)

        ACTIVE_REQUESTS.inc()
        start_time = time.time()

        try:
            response = await call_next(request)

            # Record metrics
            duration = time.time() - start_time
            path = self._normalize_path(request.url.path)

            REQUEST_COUNT.labels(
                method=request.method, path=path, status=response.status_code
            ).inc()

            REQUEST_LATENCY.labels(method=request.method, path=path).observe(duration)

            return response
        finally:
            ACTIVE_REQUESTS.dec()

    def _normalize_path(self, path: str) -> str:
        """Normalize path to reduce cardinality."""
        # Group dynamic paths
        if path.startswith("/api/"):
            return path
        if path.startswith("/static/"):
            return "/static/*"
        return path


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def record_search(mode: str, duration: float):
    """Record search-specific metrics."""
    SEARCH_COUNT.labels(mode=mode).inc()
    SEARCH_LATENCY.labels(mode=mode).observe(duration)
