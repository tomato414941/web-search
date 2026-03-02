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


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc or ""
    except Exception:
        return ""
