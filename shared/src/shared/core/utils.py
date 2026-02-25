import asyncio
import ipaddress
import socket
from urllib.parse import parse_qsl, urldefrag, urlencode, urljoin, urlsplit, urlunsplit
from typing import Optional

from cachetools import TTLCache

MAX_URL_LENGTH = 2083

# Cloud metadata endpoint
_METADATA_IPS = {"169.254.169.254"}

# SSRF DNS result cache: domain -> is_private (bool)
_SSRF_CACHE_MAX = 50_000
_SSRF_CACHE_TTL = 3600  # 1 hour
_ssrf_cache: TTLCache[str, bool] = TTLCache(
    maxsize=_SSRF_CACHE_MAX, ttl=_SSRF_CACHE_TTL
)


def is_private_ip(hostname: str) -> bool:
    """Check if hostname is an IP literal pointing to a private/reserved address.

    Does NOT perform DNS resolution — use resolve_is_private() for that.
    Returns True if the IP should be blocked.
    """
    if not hostname:
        return True
    if hostname in _METADATA_IPS:
        return True
    try:
        addr = ipaddress.ip_address(hostname)
        return (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
        )
    except ValueError:
        return False  # Not an IP literal


def resolve_is_private(hostname: str) -> bool:
    """Resolve hostname via DNS and check if any resolved IP is private/reserved.

    Returns True if the hostname resolves to a private IP (should be blocked).
    Returns True if DNS resolution fails (fail-closed).
    """
    if is_private_ip(hostname):
        return True
    try:
        results = socket.getaddrinfo(
            hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
        )
    except socket.gaierror:
        return True  # Cannot resolve → block (fail-closed)
    for _family, _type, _proto, _canonname, sockaddr in results:
        ip_str = sockaddr[0]
        if ip_str in _METADATA_IPS:
            return True
        try:
            addr = ipaddress.ip_address(ip_str)
            if (
                addr.is_private
                or addr.is_loopback
                or addr.is_link_local
                or addr.is_reserved
            ):
                return True
        except ValueError:
            return True
    return False


async def resolve_is_private_async(hostname: str) -> bool:
    """Async version of resolve_is_private using non-blocking DNS resolution."""
    if is_private_ip(hostname):
        return True
    cached = _ssrf_cache.get(hostname)
    if cached is not None:
        return cached
    try:
        loop = asyncio.get_running_loop()
        results = await loop.getaddrinfo(
            hostname, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
        )
    except socket.gaierror:
        _ssrf_cache[hostname] = True
        return True
    for _family, _type, _proto, _canonname, sockaddr in results:
        ip_str = sockaddr[0]
        if ip_str in _METADATA_IPS:
            _ssrf_cache[hostname] = True
            return True
        try:
            addr = ipaddress.ip_address(ip_str)
            if (
                addr.is_private
                or addr.is_loopback
                or addr.is_link_local
                or addr.is_reserved
            ):
                _ssrf_cache[hostname] = True
                return True
        except ValueError:
            _ssrf_cache[hostname] = True
            return True
    _ssrf_cache[hostname] = False
    return False


TRACKING_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
}


def normalize_url(
    base: str, link: str | None, *, block_private: bool = False
) -> Optional[str]:
    if not link:
        return None
    href = urljoin(base, link)
    href, _ = urldefrag(href)
    if not href.startswith(("http://", "https://")):
        return None
    if len(href) > MAX_URL_LENGTH:
        return None
    # lower scheme/host & strip common tracking params
    parts = urlsplit(href)
    host = (parts.hostname or "").lower()
    if block_private and host and is_private_ip(host):
        return None
    port = f":{parts.port}" if parts.port else ""
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k not in TRACKING_KEYS
        ]
    )
    normalized = urlunsplit((parts.scheme.lower(), host + port, parts.path, query, ""))
    if len(normalized) > MAX_URL_LENGTH:
        return None
    return normalized
