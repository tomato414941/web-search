"""Shared types for the crawler runtime storage layer."""

from dataclasses import dataclass


@dataclass
class UrlItem:
    url: str
    domain: str
    created_at: int


@dataclass
class FrontierEntry:
    url: str
    domain: str
    canonical_source: str | None
    crawl_profile: str
    priority_bucket: int
    priority_score: float
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
