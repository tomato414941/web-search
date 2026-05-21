"""Prometheus metrics endpoint and request middleware."""

import time

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from web_search_frontend.metrics import (
    ACTIVE_REQUESTS,
    ADMIN_DASHBOARD_CACHE_ACCESS,
    ADMIN_DASHBOARD_PREWARM_LAST_SUCCESS,
    ADMIN_DASHBOARD_PREWARM_TOTAL,
    REQUEST_COUNT,
    REQUEST_LATENCY,
    SEARCH_QUERY_TOTAL,
    SEARCH_RESULT_COUNT,
    SEARCH_SCORING_DURATION,
    record_admin_dashboard_cache_access,
    record_admin_dashboard_prewarm_result,
    set_admin_dashboard_last_prewarm_success,
)

__all__ = [
    "ACTIVE_REQUESTS",
    "ADMIN_DASHBOARD_CACHE_ACCESS",
    "ADMIN_DASHBOARD_PREWARM_LAST_SUCCESS",
    "ADMIN_DASHBOARD_PREWARM_TOTAL",
    "MetricsMiddleware",
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
    "SEARCH_QUERY_TOTAL",
    "SEARCH_RESULT_COUNT",
    "SEARCH_SCORING_DURATION",
    "record_admin_dashboard_cache_access",
    "record_admin_dashboard_prewarm_result",
    "router",
    "set_admin_dashboard_last_prewarm_success",
]

router = APIRouter()


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in {"/metrics", "/api/v1/metrics"}:
            return await call_next(request)

        ACTIVE_REQUESTS.inc()
        start_time = time.time()

        try:
            response = await call_next(request)
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
        if path.startswith("/api/"):
            return path
        if path.startswith("/static/"):
            return "/static/*"
        return path


@router.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
