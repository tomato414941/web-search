"""Custom Full-Text Search Engine."""

from shared.search.indexer import SearchIndexer
from shared.search.searcher import SearchEngine, SearchHit, SearchResult
from shared.search.scoring import BM25Scorer, BM25Config
from shared.search.snippet import generate_snippet, highlight_snippet, Snippet

__all__ = [
    "SearchIndexer",
    "SearchEngine",
    "SearchHit",
    "SearchResult",
    "BM25Scorer",
    "BM25Config",
    "generate_snippet",
    "highlight_snippet",
    "Snippet",
]
