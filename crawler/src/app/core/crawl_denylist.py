"""
Crawler domain denylist.

Static crawler denylist loaded from a text file.
Domains in this list are never crawled or enqueued.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_crawl_denylist(path: str | Path) -> frozenset[str]:
    """Load crawler denylist from a text file (one domain per line, # for comments)."""
    p = Path(path)
    if not p.exists():
        logger.warning("Crawler denylist not found: %s", path)
        return frozenset()

    domains: set[str] = set()
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        domains.add(line.lower())

    logger.info("Loaded crawler denylist: %d domains from %s", len(domains), path)
    return frozenset(domains)


def is_domain_denied(domain: str, denylist: frozenset[str]) -> bool:
    """Check if a domain is denied, including subdomains."""
    if not denylist:
        return False
    domain = domain.lower()
    if domain in denylist:
        return True
    parts = domain.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[i:])
        if parent in denylist:
            return True
    return False
