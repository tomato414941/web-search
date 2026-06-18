"""Build search index document projections for indexed pages."""

from typing import Protocol
from urllib.parse import urlparse

from web_search_kernel.analyzer import analyzer
from web_search_opensearch.document import SearchIndexDocument
from web_search_search_config.index_exclusions import is_search_index_excluded

SEARCH_CONTENT_MAX_CHARS = 20_000


class OpenSearchPage(Protocol):
    url: str
    title: str
    content: str


def search_index_url_metadata(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path or "/"
    return host, path


def search_projection_content(content: str) -> str:
    """Return bounded content for OpenSearch source and term projection."""
    return content[:SEARCH_CONTENT_MAX_CHARS]


def build_search_index_document(
    page: OpenSearchPage,
    *,
    page_rank: float,
    domain_rank: float,
) -> SearchIndexDocument | None:
    title = page.title or ""
    content = search_projection_content(page.content or "")
    title_terms = analyzer.tokenize(title) if title else ""
    content_terms = analyzer.tokenize(content) if content else ""

    host, path = search_index_url_metadata(page.url)
    if is_search_index_excluded(host, path):
        return None

    return {
        "url": page.url,
        "title": title,
        "content": content,
        "title_terms": title_terms,
        "content_terms": content_terms,
        "page_rank": page_rank,
        "domain_rank": domain_rank,
        "host": host,
        "path": path,
    }
