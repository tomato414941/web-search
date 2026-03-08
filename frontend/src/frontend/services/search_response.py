from typing import Any

from shared.search_kernel.searcher import SearchHit
from shared.search_kernel.snippet import generate_snippet

from frontend.services.search_query import build_snippet_terms


def build_search_hits(raw_hits: list[dict[str, Any]]) -> list[SearchHit]:
    return [
        SearchHit(
            url=hit["url"],
            title=hit["title"],
            content=hit["content"],
            score=hit["score"],
            indexed_at=hit.get("indexed_at"),
            published_at=hit.get("published_at"),
            temporal_anchor=hit.get("temporal_anchor"),
            authorship_clarity=hit.get("authorship_clarity"),
            factual_density=hit.get("factual_density"),
            origin_score=hit.get("origin_score"),
            origin_type=hit.get("origin_type"),
            author=hit.get("author"),
            organization=hit.get("organization"),
        )
        for hit in raw_hits
    ]


def append_hit_metadata(hit_dict: dict[str, Any], hit: SearchHit) -> None:
    if hit.indexed_at:
        hit_dict["indexed_at"] = hit.indexed_at
    if hit.published_at:
        hit_dict["published_at"] = hit.published_at
    if hit.temporal_anchor is not None:
        hit_dict["temporal_anchor"] = hit.temporal_anchor
    if hit.authorship_clarity is not None:
        hit_dict["authorship_clarity"] = hit.authorship_clarity
    if hit.factual_density is not None:
        hit_dict["factual_density"] = hit.factual_density
    if hit.origin_score is not None:
        hit_dict["origin_score"] = hit.origin_score
    if hit.origin_type:
        hit_dict["origin_type"] = hit.origin_type
    if hit.author:
        hit_dict["author"] = hit.author
    if hit.organization:
        hit_dict["organization"] = hit.organization


def serialize_hit(
    hit: SearchHit, search_terms: list[str], *, include_content: bool = False
) -> dict[str, Any]:
    snippet = generate_snippet(hit.content, search_terms)
    hit_dict = {
        "url": hit.url,
        "title": hit.title,
        "snip": snippet.text,
        "snip_plain": snippet.plain_text,
        "rank": hit.score,
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
