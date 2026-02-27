"""Search kernel: BM25 + vector search, indexing, analysis, and ranking."""

from shared.search_kernel.indexer import SearchIndexer
from shared.search_kernel.searcher import SearchEngine, SearchHit, SearchResult
from shared.search_kernel.scoring import BM25Scorer, BM25Config
from shared.search_kernel.snippet import generate_snippet, Snippet

__all__ = [
    "BM25Config",
    "BM25Scorer",
    "SearchEngine",
    "SearchHit",
    "SearchIndexer",
    "SearchResult",
    "Snippet",
    "generate_snippet",
]
