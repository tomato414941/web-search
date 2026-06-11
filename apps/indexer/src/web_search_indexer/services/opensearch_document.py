"""Build OpenSearch document projections for indexed pages."""

from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlparse

from web_search_indexer.services.scoring import compute_authorship_clarity
from web_search_kernel.analyzer import STOP_WORDS, analyzer
from web_search_kernel.factual_density import compute_factual_density
from web_search_search_config.index_exclusions import is_search_index_excluded


class OpenSearchPage(Protocol):
    url: str
    title: str
    content: str
    outlinks_count: int
    published_at: str | None
    author: str | None
    organization: str | None


def opensearch_url_metadata(url: str) -> tuple[str, str, bool]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path or "/"
    is_homepage = path in {"", "/"}
    return host, path, is_homepage


def link_density(outlinks_count: int, word_count: int) -> float:
    if word_count <= 0:
        return 0.0
    return round(outlinks_count / word_count, 6)


def _content_word_count(content_tokens: str) -> int:
    if not content_tokens:
        return 0
    return len(
        [t for t in content_tokens.split() if len(t) > 1 and t not in STOP_WORDS]
    )


def build_opensearch_document(
    page: OpenSearchPage,
    *,
    page_rank: float,
    domain_rank: float,
    indexed_at: str | None = None,
) -> dict[str, object] | None:
    title_tokens = analyzer.tokenize(page.title) if page.title else ""
    content_tokens = analyzer.tokenize(page.content) if page.content else ""
    word_count = _content_word_count(content_tokens)

    host, path, is_homepage = opensearch_url_metadata(page.url)
    if is_search_index_excluded(host, path):
        return None

    authorship_clarity = compute_authorship_clarity(
        page.author, page.organization, page.url
    )
    factual_density = compute_factual_density(
        page.content,
        outlinks_count=page.outlinks_count,
        word_count=word_count,
    )

    return {
        "url": page.url,
        "title": title_tokens,
        "content": content_tokens,
        "word_count": word_count,
        "link_density": link_density(page.outlinks_count, word_count),
        "title_present": bool(page.title),
        "indexed_at": indexed_at or datetime.now(UTC).isoformat(),
        "page_rank": page_rank,
        "domain_rank": domain_rank,
        "published_at": page.published_at,
        "authorship_clarity": authorship_clarity,
        "factual_density": factual_density,
        "author": page.author,
        "organization": page.organization,
        "host": host,
        "path": path,
        "is_homepage": is_homepage,
    }
