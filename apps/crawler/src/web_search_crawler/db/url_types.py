"""
Shared types and helpers for the URL store layer.
"""

import hashlib
from dataclasses import dataclass
from urllib.parse import urlparse


def url_hash(url: str) -> str:
    """Generate 16-character hash for URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def get_domain(url: str) -> str:
    """Extract domain hostname from URL (lowercase, no port)."""
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


@dataclass
class UrlItem:
    url: str
    domain: str
    created_at: int


@dataclass
class FrontierEntry:
    url: str
    domain: str
    discovered_via: str
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
