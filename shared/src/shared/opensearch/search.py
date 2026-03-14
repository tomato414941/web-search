"""OpenSearch search queries for BM25 search."""

import logging
from typing import Any

from opensearchpy import OpenSearch

from shared.opensearch.client import INDEX_NAME

logger = logging.getLogger(__name__)

CANDIDATE_LIMIT = 200
CANONICAL_HOST_BOOST = 3.0
CANONICAL_EXACT_PATH_BOOST = 5.0
CANONICAL_PATH_BOOST = 4.0
CANONICAL_HOMEPAGE_BOOST = 6.0


def search_bm25(
    client: OpenSearch,
    query_tokens: str,
    limit: int = 10,
    offset: int = 0,
    site_filter: str | None = None,
    exact_phrases: tuple[str, ...] = (),
    exclude_terms: tuple[str, ...] = (),
    exclude_phrases: tuple[str, ...] = (),
    canonical_domains: tuple[str, ...] = (),
    canonical_paths: tuple[str, ...] = (),
    required_domains: tuple[str, ...] = (),
) -> dict[str, Any]:
    """BM25 search with operator-aware filtering.

    Args:
        client: OpenSearch client
        query_tokens: Pre-tokenized query (space-separated)
        limit: Number of results to return
        offset: Pagination offset
        site_filter: Optional domain filter (e.g. "example.com")
        exact_phrases: Optional exact phrases that must match
        exclude_terms: Optional terms that must not match
        exclude_phrases: Optional exact phrases that must not match

    Returns:
        Dict with 'total', 'hits' list of {url, title, content, score}
    """
    query: dict[str, Any] = {
        "query": _build_bm25_bool_query(
            query_tokens,
            site_filter=site_filter,
            exact_phrases=exact_phrases,
            exclude_terms=exclude_terms,
            exclude_phrases=exclude_phrases,
            canonical_domains=canonical_domains,
            canonical_paths=canonical_paths,
            required_domains=required_domains,
        ),
        "from": offset,
        "size": min(limit, CANDIDATE_LIMIT),
        "_source": [
            "url",
            "host",
            "path",
            "is_homepage",
            "title",
            "content",
            "indexed_at",
            "published_at",
            "temporal_anchor",
            "authorship_clarity",
            "factual_density",
            "origin_score",
            "origin_type",
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
                "origin_score": src.get("origin_score"),
                "origin_type": src.get("origin_type"),
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


def _build_bm25_bool_query(
    query_tokens: str,
    *,
    site_filter: str | None = None,
    exact_phrases: tuple[str, ...] = (),
    exclude_terms: tuple[str, ...] = (),
    exclude_phrases: tuple[str, ...] = (),
    canonical_domains: tuple[str, ...] = (),
    canonical_paths: tuple[str, ...] = (),
    required_domains: tuple[str, ...] = (),
) -> dict[str, Any]:
    bool_query: dict[str, Any] = {}

    must_clauses = _build_positive_clauses(query_tokens, exact_phrases)
    if must_clauses:
        bool_query["must"] = must_clauses

    filter_clauses = _build_filter_clauses(site_filter, required_domains)
    if filter_clauses:
        bool_query["filter"] = filter_clauses

    must_not_clauses = _build_negative_clauses(exclude_terms, exclude_phrases)
    if must_not_clauses:
        bool_query["must_not"] = must_not_clauses

    should_clauses = _build_canonical_should_clauses(canonical_domains, canonical_paths)
    if should_clauses:
        bool_query["should"] = should_clauses

    return {"bool": bool_query}


def _build_positive_clauses(
    query_tokens: str, exact_phrases: tuple[str, ...]
) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    if query_tokens:
        clauses.append(_build_text_clause(query_tokens))
    clauses.extend(_build_phrase_clause(phrase) for phrase in exact_phrases if phrase)
    return clauses


def _build_negative_clauses(
    exclude_terms: tuple[str, ...], exclude_phrases: tuple[str, ...]
) -> list[dict[str, Any]]:
    clauses = [_build_text_clause(term) for term in exclude_terms if term]
    clauses.extend(_build_phrase_clause(phrase) for phrase in exclude_phrases if phrase)
    return clauses


def _build_filter_clauses(
    site_filter: str | None, required_domains: tuple[str, ...]
) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    if site_filter:
        clauses.append({"wildcard": {"url": {"value": f"*{site_filter}*"}}})
    if required_domains:
        domain_terms: list[dict[str, Any]] = []
        for domain in required_domains:
            domain_terms.append({"term": {"host": {"value": domain}}})
            domain_terms.append({"term": {"host": {"value": f"www.{domain}"}}})
        clauses.append({"bool": {"should": domain_terms, "minimum_should_match": 1}})
    return clauses


def _build_canonical_should_clauses(
    canonical_domains: tuple[str, ...], canonical_paths: tuple[str, ...]
) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    for domain in canonical_domains:
        if not domain:
            continue
        clauses.append(
            {"term": {"host": {"value": domain, "boost": CANONICAL_HOST_BOOST}}}
        )
        clauses.append(
            {
                "term": {
                    "host": {"value": f"www.{domain}", "boost": CANONICAL_HOST_BOOST}
                }
            }
        )
    for path in canonical_paths:
        if not path:
            continue
        if path == "/":
            clauses.append(
                {
                    "term": {
                        "is_homepage": {
                            "value": True,
                            "boost": CANONICAL_HOMEPAGE_BOOST,
                        }
                    }
                }
            )
            continue
        clauses.append(
            {"term": {"path": {"value": path, "boost": CANONICAL_EXACT_PATH_BOOST}}}
        )
        clauses.append(
            {"prefix": {"path": {"value": path, "boost": CANONICAL_PATH_BOOST}}}
        )
    return clauses


def _build_text_clause(query_tokens: str) -> dict[str, Any]:
    return {
        "multi_match": {
            "query": query_tokens,
            "fields": ["title^3", "content"],
            "type": "cross_fields",
            "operator": "or",
            "minimum_should_match": _min_should_match(query_tokens),
        }
    }


def _build_phrase_clause(phrase_tokens: str) -> dict[str, Any]:
    return {
        "multi_match": {
            "query": phrase_tokens,
            "fields": ["title^3", "content"],
            "type": "phrase",
        }
    }
