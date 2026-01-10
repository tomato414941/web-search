"""
URL Scoring Domain Logic

Implements the crawler's URL prioritization algorithm.
This is isolated domain logic that determines which URLs
should be crawled first based on various factors.
"""

import math
from urllib.parse import urlparse


def calculate_url_score(url: str, parent_score: float, domain_visits: int) -> float:
    """
    Calculate URL priority score for crawl queue.

    Higher scores = crawled sooner. Score is based on:
    1. Parent Score (Inheritance) - URLs from high-value pages are valuable
    2. Domain Freshness (Log decay) - Favor less-visited domains
    3. URL Depth (Hierarchy) - Penalize deep paths
    4. Path Keywords (Utility) - Boost/penalty based on URL patterns

    Args:
        url: The URL to score
        parent_score: Score of the page this URL was found on
        domain_visits: Number of times we've visited this domain

    Returns:
        Priority score (0-100+, higher = more important)

    Examples:
        >>> calculate_url_score("https://example.com/articles/list", 100.0, 1)
        108.0  # High score: index page, fresh domain

        >>> calculate_url_score("https://example.com/users/login", 100.0, 50)
        22.5   # Low score: login page, visited domain
    """
    # 1. Inheritance (90% of parent's value)
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
