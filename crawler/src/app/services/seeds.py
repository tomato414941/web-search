"""
Seed Service

Manages seed URL operations via the unified urls table (is_seed flag).
"""

import logging
from datetime import datetime

from app.db.url_store import UrlStore
from app.models.seeds import SeedItem, SeedListResponse

logger = logging.getLogger(__name__)


class SeedService:
    """Seed URL management service"""

    def __init__(self, url_store: UrlStore):
        self.url_store = url_store

    @staticmethod
    def _build_seed_items(rows: list[dict]) -> list[SeedItem]:
        return [
            SeedItem(
                url=row["url"],
                status=row["status"],
                created_at=datetime.fromtimestamp(row["created_at"]),
                last_crawled_at=datetime.fromtimestamp(row["last_crawled_at"])
                if row["last_crawled_at"]
                else None,
            )
            for row in rows
        ]

    def list_seeds(self) -> list[SeedItem]:
        """Get all registered seeds from the urls table."""
        return self._build_seed_items(self.url_store.get_seeds())

    def list_seeds_page(self, *, limit: int, offset: int) -> SeedListResponse:
        """Get paginated seeds with total count."""
        rows = self.url_store.get_seeds(limit=limit, offset=offset)
        return SeedListResponse(
            items=self._build_seed_items(rows),
            total=self.url_store.count_seeds(),
            limit=limit,
            offset=offset,
        )

    def add_seeds(self, urls: list[str]) -> int:
        """
        Add URLs as seeds and queue them for crawling.

        Returns:
            Number of new URLs added to the queue
        """
        added = self.url_store.add_batch(urls)
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
