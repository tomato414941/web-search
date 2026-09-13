"""Build search index document projections for indexed pages."""

from collections.abc import Iterable
from typing import Protocol, TypedDict
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


class _PreparedDocument(TypedDict):
    url: str
    title: str
    content: str
    title_terms: str
    content_terms: str
    host: str
    path: str


def search_index_url_metadata(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path or "/"
    return host, path


def search_projection_content(content: str) -> str:
    """Return bounded content for OpenSearch source and term projection."""
    return content[:SEARCH_CONTENT_MAX_CHARS]


def _prepare_search_index_document(
    page: OpenSearchPage,
) -> _PreparedDocument | None:
    title = page.title or ""
    content = search_projection_content(page.content or "")
    host, path = search_index_url_metadata(page.url)
    if is_search_index_excluded(host, path) or not (title.strip() or content.strip()):
        return None

    return {
        "url": page.url,
        "title": title,
        "content": content,
        "title_terms": analyzer.tokenize(title) if title else "",
        "content_terms": analyzer.tokenize(content) if content else "",
        "host": host,
        "path": path,
    }


def build_search_index_documents(
    pages: Iterable[OpenSearchPage],
) -> list[SearchIndexDocument]:
    """Project eligible pages and batch their embedding requests."""
    documents = [
        document
        for page in pages
        if (document := _prepare_search_index_document(page)) is not None
    ]
    if not documents:
        return []
    vectors = get_embeddings().embed(
        [f"{document['title']}\n{document['content']}" for document in documents]
    )
    return [
        {**document, "embedding": vector}
        for document, vector in zip(documents, vectors, strict=True)
    ]


def build_search_index_document(
    page: OpenSearchPage,
) -> SearchIndexDocument | None:
    documents = build_search_index_documents([page])
    return documents[0] if documents else None
