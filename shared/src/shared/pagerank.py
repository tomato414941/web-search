"""Backward-compatible re-exports. Use shared.search_kernel.pagerank instead."""

from shared.search_kernel.pagerank import (  # noqa: F401
    calculate_domain_pagerank,
    calculate_pagerank,
)
