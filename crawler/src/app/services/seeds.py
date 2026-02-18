"""
Seed Service

Manages seed URL operations via the unified urls table (is_seed flag).
"""

import logging
from datetime import datetime
from urllib.parse import urlparse

from app.db.url_store import UrlStore
from app.domain.scoring import (
    SEED_BOOST,
    get_domain_rank,
    seed_score,
)
from app.models.seeds import SeedItem

logger = logging.getLogger(__name__)


class SeedService:
    """Seed URL management service"""

    def __init__(self, url_store: UrlStore):
        self.url_store = url_store

    def list_seeds(self) -> list[SeedItem]:
        """Get all registered seeds from the urls table."""
        rows = self.url_store.get_seeds()
        return [
            SeedItem(
                url=row["url"],
                status=row["status"],
                priority=row["priority"],
                created_at=datetime.fromtimestamp(row["created_at"]),
                last_crawled_at=datetime.fromtimestamp(row["last_crawled_at"])
                if row["last_crawled_at"]
                else None,
            )
            for row in rows
        ]

    def add_seeds(self, urls: list[str], boost: float = SEED_BOOST) -> int:
        """
        Add URLs as seeds and queue them for crawling.

        Each URL's score is based on its domain_rank + boost, capped at 100.

        Returns:
            Number of new URLs added to the queue
        """
        scored = []
        for url in urls:
            domain = urlparse(url).netloc
            dr = get_domain_rank(domain)
            scored.append((url, seed_score(domain_pagerank=dr, boost=boost)))

        added = self.url_store.add_batch_scored(scored)
        self.url_store.mark_seeds(urls)
        logger.info(f"Added seeds: {len(urls)} requested, {added} newly queued")
        return added

    def delete_seeds(self, urls: list[str]) -> int:
        """
        Unmark URLs as seeds (does not remove from urls table).

        Returns:
            Number of seeds unmarked
        """
        unmarked = self.url_store.unmark_seeds(urls)
        logger.info(f"Unmarked {unmarked} seeds")
        return unmarked
