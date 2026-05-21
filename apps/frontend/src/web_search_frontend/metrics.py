"""Prometheus metric definitions shared by API and services."""

import time

from prometheus_client import Counter, Gauge, Histogram

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

ACTIVE_REQUESTS = Gauge("http_requests_active", "Number of active HTTP requests")

SEARCH_QUERY_TOTAL = Counter(
    "search_queries_total",
    "Total search queries",
    ["mode"],
)

SEARCH_RESULT_COUNT = Histogram(
    "search_result_count",
    "Number of results returned per search",
    buckets=[0, 1, 5, 10, 25, 50, 100, 500, 1000],
)

SEARCH_SCORING_DURATION = Histogram(
    "search_scoring_duration_seconds",
    "Time spent scoring search results",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
)

ADMIN_DASHBOARD_CACHE_ACCESS = Counter(
    "admin_dashboard_cache_access_total",
    "Admin dashboard cache lookups by result",
    ["result"],
)

ADMIN_DASHBOARD_PREWARM_TOTAL = Counter(
    "admin_dashboard_prewarm_total",
    "Admin dashboard prewarm attempts by result",
    ["result"],
)

ADMIN_DASHBOARD_PREWARM_LAST_SUCCESS = Gauge(
    "admin_dashboard_prewarm_last_success_timestamp_seconds",
    "Unix timestamp of the last successful admin dashboard prewarm",
)


def record_admin_dashboard_cache_access(result: str) -> None:
    ADMIN_DASHBOARD_CACHE_ACCESS.labels(result=result).inc()


def record_admin_dashboard_prewarm_result(result: str) -> None:
    ADMIN_DASHBOARD_PREWARM_TOTAL.labels(result=result).inc()


def set_admin_dashboard_last_prewarm_success(timestamp: float | None = None) -> None:
    ADMIN_DASHBOARD_PREWARM_LAST_SUCCESS.set(timestamp or time.time())
