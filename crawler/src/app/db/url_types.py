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
