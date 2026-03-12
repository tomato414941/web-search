"""Small, explicit exclusions for documents that should not enter search index."""

SEARCH_INDEX_EXCLUDED_HOSTS = frozenset(
    {
        "accounts.hatena.ne.jp",
        "stat.ameba.jp",
    }
)


def is_search_index_excluded(host: str, path: str = "/") -> bool:
    """Return True for obvious non-content hosts that should stay out of search."""
    normalized_host = (host or "").strip().lower()
    _ = path
    return normalized_host in SEARCH_INDEX_EXCLUDED_HOSTS
