"""
Search data types and query parsing.

BM25 and hybrid search are handled by OpenSearch.
Vector (semantic) search is handled by pgvector in SearchService.
"""

import re
from dataclasses import dataclass
from typing import Callable

import numpy as np

EmbeddingFunc = Callable[[str], np.ndarray]


@dataclass
class SearchHit:
    """A single search result."""

    url: str
    title: str
    content: str
    score: float


@dataclass
class SearchResult:
    """Search results with metadata."""

    query: str
    total: int
    hits: list[SearchHit]
    page: int
    per_page: int
    last_page: int


@dataclass
class ParsedQuery:
    """Parsed query with operators extracted."""

    text: str
    site_filter: str | None = None


_SITE_RE = re.compile(r"\bsite:(\S+)", re.IGNORECASE)


def parse_query(raw: str) -> ParsedQuery:
    """Extract query operators (site:) from raw query string."""
    site_filter = None
    match = _SITE_RE.search(raw)
    if match:
        site_filter = match.group(1).lower()
        raw = raw[: match.start()] + raw[match.end() :]
    return ParsedQuery(text=raw.strip(), site_filter=site_filter)
