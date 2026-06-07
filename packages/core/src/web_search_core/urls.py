"""URL identity helpers shared across services."""

import hashlib
from urllib.parse import urlparse


def url_hash(url: str) -> str:
    """Generate the stable URL identity used by database tables."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def get_domain(url: str) -> str:
    """Extract domain hostname from URL."""
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""
