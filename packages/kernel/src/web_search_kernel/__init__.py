"""Search kernel: pure search analysis and response helpers."""

from web_search_kernel.searcher import SearchHit, SearchResult
from web_search_kernel.snippet import generate_snippet, Snippet

__all__ = [
    "SearchHit",
    "SearchResult",
    "Snippet",
    "generate_snippet",
]
