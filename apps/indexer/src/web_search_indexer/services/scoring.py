"""Document metadata scoring for search ranking signals."""

from urllib.parse import urlparse


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
