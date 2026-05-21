"""Timing helpers for crawler processing stages."""

import time

from web_search_crawler.workers.types import CrawlStageTimings


def elapsed_ms(started_at: float) -> int:
    return max(0, int((time.perf_counter() - started_at) * 1000))


def timing_kwargs(timings: CrawlStageTimings) -> dict[str, int | None]:
    return {
        "precheck_ms": timings.precheck_ms,
        "robots_ms": timings.robots_ms,
        "ssrf_ms": timings.ssrf_ms,
        "crawl_delay_ms": timings.crawl_delay_ms,
        "fetch_ms": timings.fetch_ms,
        "fetch_request_ms": timings.fetch_request_ms,
        "fetch_body_read_ms": timings.fetch_body_read_ms,
        "parse_ms": timings.parse_ms,
        "submit_ms": timings.submit_ms,
        "total_ms": timings.total_ms,
    }
