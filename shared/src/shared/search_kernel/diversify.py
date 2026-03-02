"""Post-search domain diversity filtering."""

from urllib.parse import urlparse

from shared.search_kernel.searcher import SearchHit

DEFAULT_MAX_PER_DOMAIN = 3


def diversify_hits(
    hits: list[SearchHit],
    limit: int,
    max_per_domain: int = DEFAULT_MAX_PER_DOMAIN,
) -> list[SearchHit]:
    """Cap per-domain results while preserving score order.

    Args:
        hits: Score-sorted search hits (descending).
        limit: Maximum number of results to return.
        max_per_domain: Maximum hits from any single domain.
    """
    domain_counts: dict[str, int] = {}
    result: list[SearchHit] = []
    for hit in hits:
        if len(result) >= limit:
            break
        domain = _extract_domain(hit.url)
        count = domain_counts.get(domain, 0)
        if count >= max_per_domain:
            continue
        domain_counts[domain] = count + 1
        result.append(hit)
    return result


# Two-level TLDs where the registered domain is one level deeper.
_TWO_LEVEL_TLDS = frozenset(
    {
        "co.jp",
        "ne.jp",
        "or.jp",
        "ac.jp",
        "go.jp",
        "ed.jp",
        "ad.jp",
        "co.uk",
        "ac.uk",
        "org.uk",
        "gov.uk",
        "co.kr",
        "or.kr",
        "go.kr",
        "com.au",
        "net.au",
        "org.au",
        "edu.au",
        "com.br",
        "org.br",
        "net.br",
        "com.cn",
        "net.cn",
        "org.cn",
        "co.in",
        "net.in",
        "org.in",
        "co.nz",
        "net.nz",
        "org.nz",
        "com.tw",
        "org.tw",
        "net.tw",
    }
)


def _extract_domain(url: str) -> str:
    """Extract the registered domain, grouping subdomains together.

    e.g. b.hatena.ne.jp -> hatena.ne.jp, docs.github.com -> github.com
    """
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return ""
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    # Check for two-level TLD (e.g. ne.jp, co.uk)
    two_level = ".".join(parts[-2:])
    if two_level in _TWO_LEVEL_TLDS and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])
