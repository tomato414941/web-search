"""Backward-compatible re-exports. Use shared.search_kernel instead."""

from shared.search_kernel.indexer import SearchIndexer
from shared.search_kernel.searcher import SearchEngine, SearchHit, SearchResult
from shared.search_kernel.snippet import generate_snippet, Snippet

__all__ = [
    "SearchIndexer",
    "SearchEngine",
    "SearchHit",
    "SearchResult",
    "generate_snippet",
    "Snippet",
]
