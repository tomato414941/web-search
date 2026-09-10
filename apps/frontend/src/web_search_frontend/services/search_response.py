from typing import Any

from web_search_kernel.searcher import SearchHit, SearchResult
from web_search_kernel.snippet import generate_snippet

from web_search_engine.query import build_snippet_terms


def serialize_hit(
    hit: SearchHit, search_terms: list[str], *, include_content: bool = False
) -> dict[str, Any]:
    snippet = generate_snippet(hit.content, search_terms)
    hit_dict = {
        "url": hit.url,
        "title": hit.title,
        "snip": snippet.text,
        "snip_plain": snippet.plain_text,
        "score": hit.score,
    }
    if include_content and hit.content:
        hit_dict["content"] = hit.content
    return hit_dict


def build_result_payload(
    q: str, result: SearchResult, hits: list[dict[str, Any]]
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "query": q,
        "total": result.total,
        "page": result.page,
        "per_page": result.per_page,
        "last_page": result.last_page,
        "hits": hits,
    }
    return data


def format_result(
    q: str, result: SearchResult, *, include_content: bool = False
) -> dict[str, Any]:
    search_terms = build_snippet_terms(q)
    hits = [
        serialize_hit(hit, search_terms, include_content=include_content)
        for hit in result.hits
    ]
    return build_result_payload(q, result, hits)
