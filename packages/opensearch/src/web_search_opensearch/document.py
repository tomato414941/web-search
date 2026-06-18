"""Search index document contract."""

from typing import TypedDict


class SearchIndexDocument(TypedDict):
    url: str
    title: str
    content: str
    title_terms: str
    content_terms: str
    page_rank: float
    domain_rank: float
    host: str
    path: str
