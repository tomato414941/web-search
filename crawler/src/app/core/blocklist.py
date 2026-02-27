"""
Domain Blocklist

Static domain blocklist loaded from a text file.
Domains in this list are never crawled or enqueued.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_domain_blocklist(path: str | Path) -> frozenset[str]:
    """Load domain blocklist from a text file (one domain per line, # for comments)."""
    p = Path(path)
    if not p.exists():
        logger.warning("Domain blocklist not found: %s", path)
        return frozenset()

    domains: set[str] = set()
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        domains.add(line.lower())

    logger.info("Loaded domain blocklist: %d domains from %s", len(domains), path)
    return frozenset(domains)


def is_domain_blocked(domain: str, blocklist: frozenset[str]) -> bool:
    """Check if domain is blocked (supports subdomain matching).

    Example: blocklist contains "facebook.com"
      - "facebook.com" -> True
      - "www.facebook.com" -> True
      - "m.facebook.com" -> True
      - "notfacebook.com" -> False
    """
    if not blocklist:
        return False
    domain = domain.lower()
    if domain in blocklist:
        return True
    # Check if any parent domain is blocked
    parts = domain.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[i:])
        if parent in blocklist:
            return True
    return False
