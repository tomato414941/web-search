"""Search index document contract."""

from typing import TypedDict


class SearchIndexDocument(TypedDict):
    url: str
    title: str
    content: str
    indexed_at: str
    page_rank: float
    domain_rank: float
    host: str
    path: str
