"""Prometheus metrics endpoint and request middleware."""

import time

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from web_search_frontend.metrics import (
    ACTIVE_REQUESTS,
    REQUEST_COUNT,
    REQUEST_LATENCY,
    SEARCH_QUERY_TOTAL,
    SEARCH_RESULT_COUNT,
    SEARCH_SCORING_DURATION,
)

__all__ = [
    "ACTIVE_REQUESTS",
    "MetricsMiddleware",
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
    "SEARCH_QUERY_TOTAL",
    "SEARCH_RESULT_COUNT",
    "SEARCH_SCORING_DURATION",
    "router",
]

router = APIRouter()


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
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
        if path.startswith("/static/"):
            return "/static/*"
        return path


@router.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
