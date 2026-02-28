"""OpenSearch client for document indexing and deletion."""

import hashlib
import logging
from typing import Any

from opensearchpy import OpenSearch

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
            timeout=30,
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


def index_document(
    client: OpenSearch,
    url: str,
    title_tokens: str,
    content_tokens: str,
    word_count: int,
    indexed_at: str,
    authority: float = 0.0,
    embedding: list[float] | None = None,
) -> None:
    """Index a single document into OpenSearch.

    Args:
        client: OpenSearch client instance
        url: Document URL (used as document ID)
        title_tokens: Pre-tokenized title (space-separated)
        content_tokens: Pre-tokenized content (space-separated)
        word_count: Number of content tokens
        indexed_at: ISO timestamp
        authority: max(page_rank, domain_rank) score
        embedding: Optional 1536-dim vector for k-NN search
    """
    body: dict[str, Any] = {
        "url": url,
        "title": title_tokens,
        "content": content_tokens,
        "word_count": word_count,
        "indexed_at": indexed_at,
        "authority": authority,
    }
    if embedding is not None:
        body["embedding"] = embedding

    client.index(index=INDEX_NAME, id=doc_id(url), body=body)


def delete_document(client: OpenSearch, url: str) -> None:
    """Delete a document from OpenSearch by URL."""
    try:
        client.delete(index=INDEX_NAME, id=doc_id(url), ignore=[404])
    except Exception:
        logger.warning("Failed to delete %s from OpenSearch", url, exc_info=True)


def bulk_index(
    client: OpenSearch,
    documents: list[dict[str, Any]],
) -> int:
    """Bulk index documents into OpenSearch.

    Args:
        client: OpenSearch client
        documents: List of document dicts with keys matching index_document args

    Returns:
        Number of successfully indexed documents
    """
    if not documents:
        return 0

    actions: list[dict[str, Any]] = []
    for doc in documents:
        actions.append({"index": {"_index": INDEX_NAME, "_id": doc_id(doc["url"])}})
        actions.append(doc)

    resp = client.bulk(body=actions)
    errors = sum(1 for item in resp["items"] if item["index"].get("error"))
    return len(documents) - errors
