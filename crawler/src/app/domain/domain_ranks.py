"""Domain rank cache utilities used by the crawler worker."""

import logging

from shared.postgres.search import get_connection

logger = logging.getLogger(__name__)

_domain_rank_cache: dict[str, float] = {}


def load_domain_rank_cache(db_path: str) -> None:
    """Load domain_ranks table into the in-memory cache."""
    global _domain_rank_cache
    try:
        con = get_connection(db_path)
        try:
            cur = con.cursor()
            cur.execute("SELECT domain, score FROM domain_ranks")
            rows = cur.fetchall()
            cur.close()
        finally:
            con.close()
        _domain_rank_cache = {row[0]: row[1] for row in rows}
        logger.info("Loaded %d domain ranks into cache", len(_domain_rank_cache))
    except Exception as exc:
        logger.warning("Failed to load domain ranks: %s", exc)
        _domain_rank_cache = {}


def domain_rank_cache_size() -> int:
    """Return number of entries in the domain rank cache."""
    return len(_domain_rank_cache)
