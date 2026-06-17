"""Build search index document projections for indexed pages."""

from typing import Protocol
from urllib.parse import urlparse

from web_search_kernel.analyzer import analyzer
from web_search_opensearch.document import SearchIndexDocument
from web_search_search_config.index_exclusions import is_search_index_excluded


class OpenSearchPage(Protocol):
    url: str
    title: str
    content: str


def search_index_url_metadata(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path or "/"
    return host, path


def build_search_index_document(
    page: OpenSearchPage,
    *,
    page_rank: float,
    domain_rank: float,
) -> SearchIndexDocument | None:
    search_title = analyzer.tokenize(page.title) if page.title else ""
    search_content = analyzer.tokenize(page.content) if page.content else ""

    host, path = search_index_url_metadata(page.url)
    if is_search_index_excluded(host, path):
        return None

    return {
        "url": page.url,
        "title": search_title,
        "content": search_content,
        "page_rank": page_rank,
        "domain_rank": domain_rank,
        "host": host,
        "path": path,
    }
