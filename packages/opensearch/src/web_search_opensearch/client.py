"""OpenSearch client for document indexing and deletion."""

import hashlib
import logging
import os

from opensearchpy import OpenSearch

from web_search_opensearch.document import SearchIndexDocument

logger = logging.getLogger(__name__)

INDEX_NAME = "documents"
_MAX_ID_BYTES = 512

_client: OpenSearch | None = None


def get_client(url: str = "http://localhost:9200") -> OpenSearch:
    """Get or create a singleton OpenSearch client."""
    global _client
    if _client is None:
        _client = OpenSearch(
            hosts=[url],
            use_ssl=url.startswith("https"),
            verify_certs=False,
            timeout=10,
        )
    return _client


def reset_client() -> None:
    """Reset the singleton client (for testing)."""
    global _client
    _client = None


def doc_id(url: str) -> str:
    """Return a safe document ID for OpenSearch (max 512 bytes)."""
    if len(url.encode("utf-8")) <= _MAX_ID_BYTES:
        return url
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def index_name(name: str | None = None) -> str:
    """Return the target OpenSearch index or alias name."""
    return name or os.environ.get("OPENSEARCH_INDEX_NAME", INDEX_NAME)


def index_document(
    client: OpenSearch,
    document: SearchIndexDocument,
    *,
    target_index: str | None = None,
) -> None:
    """Index a single document into OpenSearch."""
    client.index(
        index=index_name(target_index),
        id=doc_id(document["url"]),
        body=dict(document),
    )


def delete_document(
    client: OpenSearch,
    url: str,
    *,
    target_index: str | None = None,
) -> None:
    """Delete a document from OpenSearch by URL."""
    try:
        client.delete(index=index_name(target_index), id=doc_id(url), ignore=[404])
    except Exception:
        logger.warning("Failed to delete %s from OpenSearch", url, exc_info=True)


def bulk_index(
    client: OpenSearch,
    documents: list[SearchIndexDocument],
    *,
    target_index: str | None = None,
) -> int:
    """Bulk index documents into OpenSearch.

    Args:
        client: OpenSearch client
        documents: Search index documents

    Returns:
        Number of successfully indexed documents
    """
    if not documents:
        return 0

    actions: list[dict[str, object]] = []
    resolved_index = index_name(target_index)
    for doc in documents:
        actions.append({"index": {"_index": resolved_index, "_id": doc_id(doc["url"])}})
        actions.append(doc)

    resp = client.bulk(body=actions)
    errors = sum(1 for item in resp["items"] if item["index"].get("error"))
    return len(documents) - errors
