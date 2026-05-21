"""Small, explicit exclusions for documents that should not enter search index."""

SEARCH_INDEX_EXCLUDED_HOSTS = frozenset(
    {
        "accounts.hatena.ne.jp",
        "stat.ameba.jp",
    }
)

SEARCH_INDEX_EXCLUDED_PATH_PREFIXES = (
    "/login",
    "/signup",
    "/account",
    "/auth",
)


def is_search_index_excluded(host: str, path: str = "/") -> bool:
    """Return True for obvious non-content hosts that should stay out of search."""
    normalized_host = (host or "").strip().lower()
    if normalized_host in SEARCH_INDEX_EXCLUDED_HOSTS:
        return True

    normalized_path = (path or "/").strip().lower()
    for prefix in SEARCH_INDEX_EXCLUDED_PATH_PREFIXES:
        if normalized_path == prefix or normalized_path.startswith(f"{prefix}/"):
            return True
    return False
