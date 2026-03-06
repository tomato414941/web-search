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
    indexed_at: str | None = None
    published_at: str | None = None
    temporal_anchor: float | None = None
    authorship_clarity: float | None = None
    factual_density: float | None = None
    origin_score: float | None = None
    origin_type: str | None = None
    author: str | None = None
    organization: str | None = None
    cluster_id: int | None = None
    sources_agreeing: int | None = None


@dataclass
class SearchResult:
    """Search results with metadata."""

    query: str
    total: int
    hits: list[SearchHit]
    page: int
    per_page: int
    last_page: int
    confidence: str | None = None
    perspective_count: int | None = None
    query_intent: str | None = None


@dataclass
class ParsedQuery:
    """Parsed query with operators extracted."""

    text: str
    site_filter: str | None = None
    exact_phrases: tuple[str, ...] = ()
    exclude_terms: tuple[str, ...] = ()
    exclude_phrases: tuple[str, ...] = ()

    def positive_text(self) -> str:
        """Return the positive query text without operators."""
        parts = [self.text, *self.exact_phrases]
        return " ".join(part for part in parts if part)


_SITE_RE = re.compile(r"(?<!\S)site:(\S+)", re.IGNORECASE)
_NEGATED_PHRASE_RE = re.compile(r'(?<!\S)-"([^"]+)"')
_PHRASE_RE = re.compile(r'"([^"]+)"')
_NEGATED_TERM_RE = re.compile(r"(?<!\S)-(\S+)")
_WHITESPACE_RE = re.compile(r"\s+")


def _extract_values(
    raw: str,
    pattern: re.Pattern[str],
    *,
    normalize: Callable[[str], str] | None = None,
) -> tuple[str, tuple[str, ...]]:
    values: list[str] = []

    def replace(match: re.Match[str]) -> str:
        value = match.group(1).strip()
        if normalize is not None:
            value = normalize(value)
        if value:
            values.append(value)
        return " "

    return pattern.sub(replace, raw), tuple(values)


def _normalize_whitespace(raw: str) -> str:
    return _WHITESPACE_RE.sub(" ", raw).strip()


def parse_query(raw: str) -> ParsedQuery:
    """Extract query operators from raw query string."""
    raw, site_filters = _extract_values(raw, _SITE_RE, normalize=str.lower)
    raw, exclude_phrases = _extract_values(raw, _NEGATED_PHRASE_RE)
    raw, exact_phrases = _extract_values(raw, _PHRASE_RE)
    raw, exclude_terms = _extract_values(raw, _NEGATED_TERM_RE)
    return ParsedQuery(
        text=_normalize_whitespace(raw),
        site_filter=site_filters[-1] if site_filters else None,
        exact_phrases=exact_phrases,
        exclude_terms=exclude_terms,
        exclude_phrases=exclude_phrases,
    )
