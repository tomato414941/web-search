"""
Crawler domain denylist.

Static crawler denylist loaded from a YAML file.
Domains in this list are never crawled or enqueued.
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def load_crawl_denylist(path: str | Path) -> frozenset[str]:
    """Load crawler denylist from a YAML file."""
    p = Path(path)
    if not p.exists():
        logger.warning("Crawler denylist not found: %s", path)
        return frozenset()

    entries = yaml.safe_load(p.read_text()) or []
    domains = {e["domain"].lower() for e in entries if "domain" in e}

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
