"""Native OpenSearch BM25 + k-NN retrieval and reciprocal rank fusion."""

from typing import Any

from opensearchpy import OpenSearch

from web_search_opensearch.client import index_name
from web_search_opensearch.mapping import SEARCH_PIPELINE

# Keep the same candidate pool across pages. This bounds accessible results,
# rather than counting all matching documents in the corpus.
RESULT_WINDOW = 200


def _text_clause(text: str, *, phrase: bool = False) -> dict[str, Any]:
    return {
        "multi_match": {
            "query": text,
            "fields": ["title_terms^3", "content_terms"],
            "type": "phrase" if phrase else "best_fields",
        }
    }


def operator_filter(
    *,
    site: str | None,
    phrases: tuple[str, ...],
    excluded_terms: tuple[str, ...],
    excluded_phrases: tuple[str, ...],
) -> dict[str, Any]:
    """Apply explicit operators to both retrieval branches before fusion."""
    filters = [_text_clause(phrase, phrase=True) for phrase in phrases]
    if site:
        filters.append(
            {
                "bool": {
                    "should": [
                        {"term": {"host": site}},
                        {"wildcard": {"host": {"value": f"*.{site}"}}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    excluded = [
        *(_text_clause(term) for term in excluded_terms),
        *(_text_clause(phrase, phrase=True) for phrase in excluded_phrases),
    ]
    return (
        {"bool": {"filter": filters, "must_not": excluded}}
        if filters or excluded
        else {"match_all": {}}
    )


def search_hybrid(
    client: OpenSearch,
    *,
    query_tokens: str,
    vector: list[float],
    limit: int,
    offset: int,
    filters: dict[str, Any],
    target_index: str,
) -> dict[str, Any]:
    if limit < 1 or offset < 0 or offset >= RESULT_WINDOW:
        raise ValueError(f"Requested page exceeds the {RESULT_WINDOW}-result window")
    body = {
        "query": {
            "hybrid": {
                "queries": [
                    {
                        "bool": {
                            "must": [_text_clause(query_tokens)],
                            "filter": [filters],
                        }
                    },
                    {
                        "knn": {
                            "embedding": {
                                "vector": vector,
                                "k": RESULT_WINDOW,
                                "filter": filters,
                            }
                        }
                    },
                ],
                "pagination_depth": RESULT_WINDOW,
            }
        },
        "from": offset,
        "size": min(limit, RESULT_WINDOW - offset),
        "_source": ["url", "title", "content"],
        "track_total_hits": True,
    }
    response = client.search(
        index=index_name(target_index),
        body=body,
        params={
            "search_pipeline": SEARCH_PIPELINE,
            "allow_partial_search_results": "false",
        },
    )
    if response.get("timed_out") or response.get("_shards", {}).get("failed", 0):
        raise RuntimeError("Hybrid search did not complete")
    return {
        "total": min(response["hits"]["total"]["value"], RESULT_WINDOW),
        "hits": [
            {**hit["_source"], "score": hit["_score"]}
            for hit in response["hits"]["hits"]
        ],
    }
