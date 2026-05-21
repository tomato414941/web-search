"""
URL pattern filters.

Filters loaded from a YAML file to skip URLs matching known
non-content patterns (images, binaries, auth pages, etc.).
"""

import logging
from pathlib import Path
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)


class UrlFilter:
    """Compiled URL filter for fast matching."""

    def __init__(
        self,
        extension_filters: frozenset[str],
        contains_filters: tuple[str, ...],
    ):
        self._extensions = extension_filters
        self._contains = contains_filters

    def is_filtered(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()

        # Extension check (path only, before query string)
        dot_idx = path.rfind(".")
        if dot_idx != -1 and path[dot_idx:] in self._extensions:
            return True

        # Contains check (full URL, lowered)
        url_lower = url.lower()
        for pat in self._contains:
            if pat in url_lower:
                return True

        return False


def load_url_filters(path: str | Path) -> UrlFilter:
    """Load URL filters from a YAML file."""
    p = Path(path)
    if not p.exists():
        logger.warning("URL filters not found: %s", path)
        return UrlFilter(frozenset(), ())

    entries = yaml.safe_load(p.read_text()) or []

    extensions: set[str] = set()
    contains: list[str] = []

    for entry in entries:
        pattern = entry.get("pattern", "")
        match_type = entry.get("match_type", "")

        if match_type == "extension":
            ext = pattern if pattern.startswith(".") else f".{pattern}"
            extensions.add(ext.lower())
        elif match_type == "contains":
            contains.append(pattern.lower())

    filt = UrlFilter(frozenset(extensions), tuple(contains))
    logger.info(
        "Loaded URL filters: %d extensions, %d contains from %s",
        len(extensions),
        len(contains),
        path,
    )
    return filt
