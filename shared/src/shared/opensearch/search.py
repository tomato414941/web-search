"""OpenSearch search queries for BM25 and hybrid search."""

import logging
from typing import Any

from opensearchpy import OpenSearch

from shared.opensearch.client import INDEX_NAME

logger = logging.getLogger(__name__)

CANDIDATE_LIMIT = 200


def search_bm25(
    client: OpenSearch,
    query_tokens: str,
    limit: int = 10,
    offset: int = 0,
    site_filter: str | None = None,
) -> dict[str, Any]:
    """BM25 search with authority and freshness boosting.

    Args:
        client: OpenSearch client
        query_tokens: Pre-tokenized query (space-separated)
        limit: Number of results to return
        offset: Pagination offset
        site_filter: Optional domain filter (e.g. "example.com")

    Returns:
        Dict with 'total', 'hits' list of {url, title, content, score}
    """
    must_clause: dict[str, Any] = {
        "multi_match": {
            "query": query_tokens,
            "fields": ["title^3", "content"],
            "type": "cross_fields",
            "operator": "and",
            "minimum_should_match": _min_should_match(query_tokens),
        }
    }

    filter_clauses: list[dict[str, Any]] = []
    if site_filter:
        filter_clauses.append({"wildcard": {"url": {"value": f"*{site_filter}*"}}})

    query: dict[str, Any] = {
        "query": {
            "function_score": {
                "query": {
                    "bool": {
                        "must": [must_clause],
                        "filter": filter_clauses,
                    }
                },
                "functions": [
                    {
                        "field_value_factor": {
                            "field": "authority",
                            "modifier": "none",
                            "factor": 0.5,
                            "missing": 0,
                        },
                        "weight": 1,
                    },
                    {
                        "field_value_factor": {
                            "field": "temporal_anchor",
                            "modifier": "none",
                            "factor": 1,
                            "missing": 0.5,
                        },
                        "weight": 0.1,
                    },
                    {
                        "field_value_factor": {
                            "field": "factual_density",
                            "modifier": "none",
                            "factor": 1,
                            "missing": 0.5,
                        },
                        "weight": 0.3,
                    },
                ],
                "score_mode": "sum",
                "boost_mode": "multiply",
            }
        },
        "from": offset,
        "size": min(limit, CANDIDATE_LIMIT),
        "_source": [
            "url",
            "title",
            "content",
            "indexed_at",
            "published_at",
            "temporal_anchor",
            "authorship_clarity",
            "factual_density",
            "author",
            "organization",
        ],
    }

    resp = client.search(index=INDEX_NAME, body=query)

    total = resp["hits"]["total"]["value"]
    hits = []
    for hit in resp["hits"]["hits"]:
        src = hit["_source"]
        hits.append(
            {
                "url": src["url"],
                "title": src.get("title", ""),
                "content": src.get("content", ""),
                "score": hit["_score"],
                "indexed_at": src.get("indexed_at"),
                "published_at": src.get("published_at"),
                "temporal_anchor": src.get("temporal_anchor"),
                "authorship_clarity": src.get("authorship_clarity"),
                "factual_density": src.get("factual_density"),
                "author": src.get("author"),
                "organization": src.get("organization"),
            }
        )

    return {"total": total, "hits": hits}


def search_hybrid(
    client: OpenSearch,
    query_tokens: str,
    embedding: list[float],
    limit: int = 10,
    offset: int = 0,
    site_filter: str | None = None,
) -> dict[str, Any]:
    """Hybrid search combining BM25 and k-NN vector search.

    Uses OpenSearch's hybrid query with RRF normalization.

    Args:
        client: OpenSearch client
        query_tokens: Pre-tokenized query (space-separated)
        embedding: Query embedding vector (1536 dims)
        limit: Number of results
        offset: Pagination offset
        site_filter: Optional domain filter

    Returns:
        Dict with 'total', 'hits' list
    """
    filter_clauses: list[dict[str, Any]] = []
    if site_filter:
        filter_clauses.append({"wildcard": {"url": {"value": f"*{site_filter}*"}}})

    bm25_query: dict[str, Any] = {
        "multi_match": {
            "query": query_tokens,
            "fields": ["title^3", "content"],
            "type": "cross_fields",
            "operator": "and",
            "minimum_should_match": _min_should_match(query_tokens),
        }
    }

    knn_query: dict[str, Any] = {
        "knn": {
            "embedding": {
                "vector": embedding,
                "k": min(limit * 2, CANDIDATE_LIMIT),
            }
        }
    }

    query: dict[str, Any] = {
        "query": {
            "bool": {
                "should": [bm25_query, knn_query],
                "filter": filter_clauses,
                "minimum_should_match": 1,
            }
        },
        "from": offset,
        "size": min(limit, CANDIDATE_LIMIT),
        "_source": [
            "url",
            "title",
            "content",
            "indexed_at",
            "published_at",
            "temporal_anchor",
            "authorship_clarity",
            "factual_density",
            "author",
            "organization",
        ],
    }

    resp = client.search(index=INDEX_NAME, body=query)

    total = resp["hits"]["total"]["value"]
    hits = []
    for hit in resp["hits"]["hits"]:
        src = hit["_source"]
        hits.append(
            {
                "url": src["url"],
                "title": src.get("title", ""),
                "content": src.get("content", ""),
                "score": hit["_score"],
                "indexed_at": src.get("indexed_at"),
                "published_at": src.get("published_at"),
                "temporal_anchor": src.get("temporal_anchor"),
                "authorship_clarity": src.get("authorship_clarity"),
                "factual_density": src.get("factual_density"),
                "author": src.get("author"),
                "organization": src.get("organization"),
            }
        )

    return {"total": total, "hits": hits}


def _min_should_match(query_tokens: str) -> str:
    """Determine minimum_should_match based on token count."""
    token_count = len(query_tokens.split())
    if token_count <= 2:
        return "100%"
    elif token_count <= 5:
        return "60%"
    else:
        return "50%"
