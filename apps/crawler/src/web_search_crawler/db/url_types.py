"""Shared types for the crawler runtime storage layer."""

from dataclasses import dataclass


@dataclass
class CrawlTask:
    url: str
    domain: str
    created_at: int


@dataclass
class CrawlScheduleEntry:
    url: str
    domain: str
    priority_bucket: int
    status: str
    next_fetch_at: int


@dataclass
class DomainState:
    domain: str
    next_request_at: int
    crawl_delay_sec: float
    backoff_until: int | None
    fail_streak: int
    inflight_leases: int
