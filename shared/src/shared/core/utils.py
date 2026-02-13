from urllib.parse import parse_qsl, urldefrag, urlencode, urljoin, urlsplit, urlunsplit
from typing import Optional

MAX_URL_LENGTH = 2083

TRACKING_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
}


def normalize_url(base: str, link: str | None) -> Optional[str]:
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
