"""Build search index document projections for indexed pages."""

from typing import Protocol
from urllib.parse import urlparse

from web_search_kernel.analyzer import analyzer
from web_search_opensearch.document import SearchIndexDocument
from web_search_opensearch.embeddings import get_embeddings
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
) -> SearchIndexDocument | None:
    title = page.title or ""
    content = search_projection_content(page.content or "")
    title_terms = analyzer.tokenize(title) if title else ""
    content_terms = analyzer.tokenize(content) if content else ""

    host, path = search_index_url_metadata(page.url)
    if is_search_index_excluded(host, path) or not (title.strip() or content.strip()):
        return None

    return {
        "url": page.url,
        "title": title,
        "content": content,
        "title_terms": title_terms,
        "content_terms": content_terms,
        "embedding": get_embeddings().query(f"{title}\n{content}"),
        "host": host,
        "path": path,
    }
