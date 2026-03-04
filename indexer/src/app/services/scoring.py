"""Document metadata scoring for search ranking signals."""

import math
from urllib.parse import urlparse


def compute_content_quality(
    word_count: int,
    outlinks_count: int,
    title: str,
    published_at: str | None,
) -> float:
    """Compute content quality score (0.0-1.0).

    Based on Boilerpipe's shallow text features (Kohlschutter 2010).
    """
    # Text substance (log scale, 1000 words -> 1.0)
    text_score = min(1.0, math.log10(word_count + 1) / 3.0)

    # Link density penalty (link-heavy pages are likely aggregation)
    if word_count > 0:
        link_ratio = outlinks_count / word_count
        link_penalty = max(0.3, 1.0 - link_ratio * 3)
    else:
        link_penalty = 0.3

    # Structure bonus (structured content tends to be higher quality)
    structure = 1.0
    if title and len(title) > 5:
        structure += 0.1
    if published_at:
        structure += 0.1

    return round(min(1.0, text_score * link_penalty * structure), 4)


def compute_temporal_anchor(published_at: str | None) -> float:
    """Score how well the document's time context is grounded.

    AI agents need to know WHEN information was true.
    This does NOT boost fresh content — it scores temporal transparency.
    The AI agent decides freshness relevance, not the search engine.
    """
    if published_at:
        return 1.0
    return 0.2


UGC_DOMAINS = frozenset(
    [
        "reddit.com",
        "twitter.com",
        "x.com",
        "news.ycombinator.com",
        "stackoverflow.com",
        "stackexchange.com",
        "quora.com",
        "medium.com",
        "dev.to",
        "github.com",
    ]
)


def compute_authorship_clarity(
    author: str | None,
    organization: str | None,
    url: str,
) -> float:
    """Score how clearly the authorship is identified.

    AI agents need to know WHO wrote this to assess reliability.
    """
    domain = urlparse(url).netloc.lower()
    base_domain = ".".join(domain.rsplit(".", 2)[-2:])

    if base_domain in UGC_DOMAINS:
        return 0.3

    if author and organization:
        return 1.0
    if author:
        return 0.8
    if organization:
        return 0.6
    return 0.1
