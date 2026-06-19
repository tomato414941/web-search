"""OpenSearch search queries for BM25 search."""

import logging
from dataclasses import dataclass
from typing import Any

from opensearchpy import OpenSearch

from web_search_opensearch.client import index_name

logger = logging.getLogger(__name__)

CANDIDATE_LIMIT = 200


@dataclass(frozen=True)
class HostPathBoosts:
    hosts: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    host_boost: float = 1.0
    exact_path_boost: float = 1.0
    path_prefix_boost: float = 1.0
    homepage_boost: float = 1.0


@dataclass(frozen=True)
class SubjectPhraseBoosts:
    subjects: tuple[str, str] | None = None
    subjects_boost: float = 1.0
    title_boost: float = 1.0
    phrase_boost: float = 1.0
    cue_boost: float = 1.0


@dataclass(frozen=True)
class RetrievalBoosts:
    host_path: HostPathBoosts | None = None
    subject_phrase: SubjectPhraseBoosts | None = None


def search_bm25(
    client: OpenSearch,
    query_tokens: str,
    limit: int = 10,
    offset: int = 0,
    site_filter: str | None = None,
    exact_phrases: tuple[str, ...] = (),
    exclude_terms: tuple[str, ...] = (),
    exclude_phrases: tuple[str, ...] = (),
    required_domains: tuple[str, ...] = (),
    retrieval_boosts: RetrievalBoosts | None = None,
    target_index: str | None = None,
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
            required_domains=required_domains,
            retrieval_boosts=retrieval_boosts,
        ),
        "from": offset,
        "size": min(limit, CANDIDATE_LIMIT),
        "_source": [
            "url",
            "host",
            "path",
            "title",
            "content",
            "page_rank",
            "domain_rank",
        ],
    }

    resp = client.search(index=index_name(target_index), body=query)

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
                "page_rank": src.get("page_rank"),
                "domain_rank": src.get("domain_rank"),
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
    required_domains: tuple[str, ...] = (),
    retrieval_boosts: RetrievalBoosts | None = None,
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

    should_clauses = [
        *_build_subject_phrase_should_clauses(
            retrieval_boosts.subject_phrase if retrieval_boosts else None
        ),
        *_build_host_path_should_clauses(
            retrieval_boosts.host_path if retrieval_boosts else None
        ),
    ]
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
            domain_terms.append({"prefix": {"url": {"value": f"https://{domain}/"}}})
            domain_terms.append({"prefix": {"url": {"value": f"http://{domain}/"}}})
            domain_terms.append(
                {"prefix": {"url": {"value": f"https://www.{domain}/"}}}
            )
            domain_terms.append({"prefix": {"url": {"value": f"http://www.{domain}/"}}})
        clauses.append({"bool": {"should": domain_terms, "minimum_should_match": 1}})
    return clauses


def _build_host_path_should_clauses(
    boosts: HostPathBoosts | None,
) -> list[dict[str, Any]]:
    if boosts is None:
        return []

    clauses: list[dict[str, Any]] = []
    for domain in boosts.hosts:
        if not domain:
            continue
        clauses.append(
            {"term": {"host": {"value": domain, "boost": boosts.host_boost}}}
        )
        clauses.append(
            {"term": {"host": {"value": f"www.{domain}", "boost": boosts.host_boost}}}
        )
    for path in boosts.paths:
        if not path:
            continue
        clauses.append(
            {
                "term": {
                    "path": {
                        "value": path,
                        "boost": boosts.homepage_boost
                        if path == "/"
                        else boosts.exact_path_boost,
                    }
                }
            }
        )
        if path == "/":
            continue
        clauses.append(
            {"prefix": {"path": {"value": path, "boost": boosts.path_prefix_boost}}}
        )
    return clauses


def _build_text_clause(
    query_tokens: str, *, boost: float | None = None
) -> dict[str, Any]:
    clause = {
        "multi_match": {
            "query": query_tokens,
            "fields": ["title_terms^3", "content_terms"],
            "type": "cross_fields",
            "operator": "or",
            "minimum_should_match": _min_should_match(query_tokens),
        }
    }
    if boost is not None:
        clause["multi_match"]["boost"] = boost
    return clause


def _build_phrase_clause(
    phrase_tokens: str, *, boost: float | None = None
) -> dict[str, Any]:
    clause = {
        "multi_match": {
            "query": phrase_tokens,
            "fields": ["title_terms^3", "content_terms"],
            "type": "phrase",
        }
    }
    if boost is not None:
        clause["multi_match"]["boost"] = boost
    return clause


def _build_subject_phrase_should_clauses(
    boosts: SubjectPhraseBoosts | None,
) -> list[dict[str, Any]]:
    if boosts is None or boosts.subjects is None:
        return []

    left = boosts.subjects[0].strip().lower()
    right = boosts.subjects[1].strip().lower()
    if not left or not right:
        return []

    phrases = (
        f"{left} vs {right}",
        f"{right} vs {left}",
        f"{left} versus {right}",
        f"{right} versus {left}",
    )
    subject_query = f"{left} {right}"
    cue_query = f"{left} {right} vs versus compare comparison"

    return [
        {
            "multi_match": {
                "query": subject_query,
                "fields": ["title_terms^6", "content_terms"],
                "type": "cross_fields",
                "operator": "and",
                "boost": boosts.title_boost,
            }
        },
        {
            "multi_match": {
                "query": cue_query,
                "fields": ["title_terms^4"],
                "type": "cross_fields",
                "operator": "or",
                "minimum_should_match": "50%",
                "boost": boosts.cue_boost,
            }
        },
        {
            "bool": {
                "must": [
                    _build_text_clause(left),
                    _build_text_clause(right),
                ],
                "boost": boosts.subjects_boost,
            }
        },
        *[
            _build_phrase_clause(phrase, boost=boosts.phrase_boost)
            for phrase in phrases
        ],
    ]
