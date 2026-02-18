"""
URL Scoring Domain Logic

Implements the crawler's URL prioritization algorithm.
All scores are normalized to a 0-100 scale.
"""

import logging
import math
import re
from urllib.parse import urlparse

from shared.db.search import get_connection

logger = logging.getLogger(__name__)

# Default base score when domain_rank is unknown
DEFAULT_BASE = 15.0

# Max score inherited from parent page
MAX_INHERITED = 40.0

# Boost values added to domain_base for seed URLs (capped at 100)
SEED_BOOST = 20.0
MANUAL_CRAWL_BOOST = 30.0
TRANCO_BOOST = 10.0

# Path keyword patterns (word-boundary aware)
_BOOST_RE = re.compile(
    r"(?:^|[/_-])(?:list|index|category|wiki|docs|guide|faq|about)(?:$|[/_\-.])",
    re.IGNORECASE,
)
_PENALTY_RE = re.compile(
    r"(?:^|[/_-])(?:login|signup|register|logout|archive|tags?|admin|cart|checkout|print|raw|diff|edit|action)(?:$|[/_\-.])",
    re.IGNORECASE,
)

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


def _domain_base(domain_pagerank: float | None) -> float:
    """Map domain PageRank (0-1) to score (0-100) on a log scale.

    Examples: twitter(1.0)→100, github(0.39)→86, avg(0.003)→20
    """
    if domain_pagerank is None or domain_pagerank < 0:
        return DEFAULT_BASE
    return min(100.0, (math.log10(domain_pagerank * 1000.0 + 1) / 3.0) * 100.0)


def _base_score(domain_pagerank: float | None, parent_score: float) -> float:
    """Compute base score: domain_rank preferred, parent inheritance capped."""
    if domain_pagerank is not None:
        return _domain_base(domain_pagerank)
    inherited = min(parent_score * 0.8, MAX_INHERITED)
    return max(DEFAULT_BASE, inherited)


def _diversity_factor(domain_visits: int) -> float:
    """Gentle decay to diversify across domains. Floor at 0.6."""
    if domain_visits <= 0:
        return 1.0
    return max(0.6, 1.0 - 0.1 * math.log10(domain_visits))


def _depth_factor(url: str) -> float:
    """Penalize deep URL paths. Floor at 0.5."""
    path = urlparse(url).path
    depth = max(0, path.count("/") - 1)
    return max(0.5, 0.9**depth)


def _path_factor(url: str) -> float:
    """Boost/penalize based on URL path keywords (word-boundary matching)."""
    path = urlparse(url).path
    if _PENALTY_RE.search(path):
        return 0.5
    if _BOOST_RE.search(path):
        return 1.2
    return 1.0


def calculate_url_score(
    url: str,
    parent_score: float,
    domain_visits: int,
    domain_pagerank: float | None = None,
) -> float:
    """
    Calculate URL priority score for crawl queue.

    All scores are on a 0-100 scale. Higher = crawled sooner.

    Args:
        url: The URL to score
        parent_score: Score of the page this URL was found on
        domain_visits: Number of times we've visited this domain
        domain_pagerank: Domain-level PageRank score (None if unavailable)

    Returns:
        Priority score (0-100, higher = more important)
    """
    base = _base_score(domain_pagerank, parent_score)
    return min(
        100.0,
        round(
            base
            * _diversity_factor(domain_visits)
            * _depth_factor(url)
            * _path_factor(url),
            2,
        ),
    )


def seed_score(
    domain_pagerank: float | None = None,
    boost: float = SEED_BOOST,
) -> float:
    """Calculate score for a seed URL.

    Uses domain_base + boost, capped at 100.

    Args:
        domain_pagerank: Domain-level PageRank (None if unknown)
        boost: Extra points for seed type (SEED_BOOST, MANUAL_CRAWL_BOOST, TRANCO_BOOST)

    Returns:
        Priority score (0-100)
    """
    return min(100.0, _domain_base(domain_pagerank) + boost)
