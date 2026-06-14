from typing import Any

from web_search_kernel.searcher import SearchHit
from web_search_kernel.snippet import generate_snippet

from web_search_frontend.services.search_query import build_snippet_terms


def build_search_hits(raw_hits: list[dict[str, Any]]) -> list[SearchHit]:
    return [
        SearchHit(
            url=hit["url"],
            title=hit["title"],
            content=hit["content"],
            score=hit["score"],
            indexed_at=hit.get("indexed_at"),
            published_at=hit.get("published_at"),
            page_rank=hit.get("page_rank"),
            domain_rank=hit.get("domain_rank"),
        )
        for hit in raw_hits
    ]


def append_hit_metadata(hit_dict: dict[str, Any], hit: SearchHit) -> None:
    if hit.indexed_at:
        hit_dict["indexed_at"] = hit.indexed_at
    if hit.published_at:
        hit_dict["published_at"] = hit.published_at
    if hit.page_rank is not None:
        hit_dict["page_rank"] = hit.page_rank
    if hit.domain_rank is not None:
        hit_dict["domain_rank"] = hit.domain_rank


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
    append_hit_metadata(hit_dict, hit)
    return hit_dict


def build_result_payload(
    q: str, result: Any, hits: list[dict[str, Any]]
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
    q: str, result: Any, *, include_content: bool = False
) -> dict[str, Any]:
    search_terms = build_snippet_terms(q)
    hits = [
        serialize_hit(hit, search_terms, include_content=include_content)
        for hit in result.hits
    ]
    return build_result_payload(q, result, hits)
