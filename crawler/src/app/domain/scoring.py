"""
URL Scoring Domain Logic

Implements the crawler's URL prioritization algorithm.
This is isolated domain logic that determines which URLs
should be crawled first based on various factors.
"""

import logging
import math
from urllib.parse import urlparse

from shared.db.search import get_connection

logger = logging.getLogger(__name__)

# Fixed priority constants (replace user-specified priority)
SEED_DEFAULT_SCORE = 100.0
MANUAL_CRAWL_SCORE = 1000.0
TRANCO_IMPORT_SCORE = 50.0

# Normalization scale: domain_rank * N_domains * PAGERANK_SCALE
# Average domain → ~100 score
PAGERANK_SCALE = 100.0

# Domain PageRank cache
_domain_rank_cache: dict[str, float] = {}


def load_domain_rank_cache(db_path: str) -> None:
    """Load domain_ranks table into memory cache."""
    global _domain_rank_cache
    try:
        con = get_connection(db_path)
        cur = con.cursor()
        cur.execute("SELECT domain, score FROM domain_ranks")
        rows = cur.fetchall()
        cur.close()
        con.close()
        _domain_rank_cache = {row[0]: row[1] for row in rows}
        logger.info(f"Loaded {len(_domain_rank_cache)} domain ranks into cache")
    except Exception as e:
        logger.warning(f"Failed to load domain ranks: {e}")
        _domain_rank_cache = {}


def get_domain_rank(domain: str) -> float | None:
    """Get domain PageRank from cache."""
    return _domain_rank_cache.get(domain)


def calculate_url_score(
    url: str,
    parent_score: float,
    domain_visits: int,
    domain_pagerank: float | None = None,
) -> float:
    """
    Calculate URL priority score for crawl queue.

    Higher scores = crawled sooner. Score is based on:
    1. Base Score - Domain PageRank (if available) or parent inheritance
    2. Domain Freshness (Log decay) - Favor less-visited domains
    3. URL Depth (Hierarchy) - Penalize deep paths
    4. Path Keywords (Utility) - Boost/penalty based on URL patterns

    Args:
        url: The URL to score
        parent_score: Score of the page this URL was found on
        domain_visits: Number of times we've visited this domain
        domain_pagerank: Domain-level PageRank score (None if unavailable)

    Returns:
        Priority score (0-100+, higher = more important)
    """
    # 1. Base score
    if domain_pagerank is not None and _domain_rank_cache:
        # Normalize: domain_rank * N_domains * scale → average domain ≈ 100
        n_domains = len(_domain_rank_cache)
        base = domain_pagerank * n_domains * PAGERANK_SCALE * 0.9
    else:
        # Fallback: inheritance from parent (bootstrap period)
        base = parent_score * 0.9

    # 2. Domain Freshness
    # 1st visit: 1.0, 10th: ~0.5, 100th: ~0.33
    domain_factor = 1.0 / (1.0 + math.log10(domain_visits + 1))

    # 3. URL Depth
    # Penalize deep hierarchy (e.g., /a/b/c/d/e)
    path = urlparse(url).path
    depth = max(0, path.count("/") - 1)
    depth_factor = 0.9**depth

    # 4. Path Keywords
    # Boost catalog/index pages, penalize user-specific pages
    path_lower = path.lower()
    path_factor = 1.0

    # High-value paths (likely to have many outlinks)
    if "list" in path_lower or "index" in path_lower or "category" in path_lower:
        path_factor = 1.2

    # Low-value paths (user-specific, no useful content)
    if (
        "login" in path_lower
        or "signup" in path_lower
        or "archive" in path_lower
        or "tag" in path_lower
    ):
        path_factor = 0.5

    return base * domain_factor * depth_factor * path_factor
