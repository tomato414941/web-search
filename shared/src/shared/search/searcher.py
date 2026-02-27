"""Backward-compatible re-exports. Use shared.search_kernel.searcher instead."""

from shared.search_kernel.searcher import (  # noqa: F401
    SearchEngine,
    SearchHit,
    SearchResult,
    parse_query,
)
