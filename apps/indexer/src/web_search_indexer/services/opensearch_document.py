"""Build OpenSearch document projections for indexed pages."""

from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlparse

from web_search_kernel.analyzer import analyzer
from web_search_search_config.index_exclusions import is_search_index_excluded


class OpenSearchPage(Protocol):
    url: str
    title: str
    content: str
    published_at: str | None


def opensearch_url_metadata(url: str) -> tuple[str, str, bool]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path or "/"
    is_homepage = path in {"", "/"}
    return host, path, is_homepage


def build_opensearch_document(
    page: OpenSearchPage,
    *,
    page_rank: float,
    domain_rank: float,
    indexed_at: str | None = None,
) -> dict[str, object] | None:
    title_tokens = analyzer.tokenize(page.title) if page.title else ""
    content_tokens = analyzer.tokenize(page.content) if page.content else ""

    host, path, is_homepage = opensearch_url_metadata(page.url)
    if is_search_index_excluded(host, path):
        return None

    return {
        "url": page.url,
        "title": title_tokens,
        "content": content_tokens,
        "indexed_at": indexed_at or datetime.now(UTC).isoformat(),
        "page_rank": page_rank,
        "domain_rank": domain_rank,
        "published_at": page.published_at,
        "host": host,
        "path": path,
        "is_homepage": is_homepage,
    }
