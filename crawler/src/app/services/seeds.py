"""
Seed Service

Manages seed URL storage and requeueing operations.
Seeds are stored in Redis Hash for persistence.
"""

import json
import logging
from datetime import datetime

from shared.db.redis import enqueue_batch
from app.core.config import settings
from app.models.seeds import SeedItem

logger = logging.getLogger(__name__)


class SeedService:
    """Seed URL management service"""

    def __init__(self, redis_client):
        self.redis = redis_client

    def list_seeds(self) -> list[SeedItem]:
        """
        Get all registered seeds.

        Returns:
            List of SeedItem objects
        """
        seeds_data = self.redis.hgetall(settings.CRAWL_SEEDS_KEY)
        result = []
        for url, data_json in seeds_data.items():
            try:
                data = json.loads(data_json)
                result.append(
                    SeedItem(
                        url=url,
                        added_at=datetime.fromisoformat(data["added_at"]),
                        priority=data.get("priority", 100.0),
                        last_queued=datetime.fromisoformat(data["last_queued"])
                        if data.get("last_queued")
                        else None,
                    )
                )
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Invalid seed data for {url}: {e}")
                continue
        return sorted(result, key=lambda x: x.added_at, reverse=True)

    def add_seeds(self, urls: list[str], priority: float = 100.0) -> int:
        """
        Add URLs as seeds and queue them for crawling.

        Args:
            urls: List of URLs to add
            priority: Priority score for queuing

        Returns:
            Number of new seeds added
        """
        now = datetime.utcnow()
        added = 0
        pipe = self.redis.pipeline()
        new_urls = []

        for url in urls:
            if not self.redis.hexists(settings.CRAWL_SEEDS_KEY, url):
                data = {
                    "added_at": now.isoformat(),
                    "priority": priority,
                    "last_queued": now.isoformat(),
                }
                pipe.hset(settings.CRAWL_SEEDS_KEY, url, json.dumps(data))
                new_urls.append(url)
                added += 1
            else:
                # Update last_queued for existing seeds
                existing = self.redis.hget(settings.CRAWL_SEEDS_KEY, url)
                if existing:
                    data = json.loads(existing)
                    data["last_queued"] = now.isoformat()
                    pipe.hset(settings.CRAWL_SEEDS_KEY, url, json.dumps(data))
                new_urls.append(url)

        pipe.execute()

        # Queue all URLs (new and existing)
        if new_urls:
            enqueue_batch(
                self.redis,
                new_urls,
                parent_score=priority,
                queue_key=settings.CRAWL_QUEUE_KEY,
                seen_key=settings.CRAWL_SEEN_KEY,
            )

        logger.info(f"Added {added} new seeds, queued {len(new_urls)} URLs")
        return added

    def delete_seeds(self, urls: list[str]) -> int:
        """
        Remove URLs from seed list.

        Args:
            urls: List of URLs to remove

        Returns:
            Number of seeds removed
        """
        deleted = 0
        for url in urls:
            result = self.redis.hdel(settings.CRAWL_SEEDS_KEY, url)
            deleted += result
        logger.info(f"Deleted {deleted} seeds")
        return deleted

    def requeue_all(self, force: bool = False) -> int:
        """
        Re-add all seeds to the crawl queue.

        Args:
            force: If True, remove from crawl:seen first to allow re-crawling

        Returns:
            Number of URLs queued
        """
        seeds_data = self.redis.hgetall(settings.CRAWL_SEEDS_KEY)
        if not seeds_data:
            return 0

        now = datetime.utcnow()
        urls_to_queue = []
        pipe = self.redis.pipeline()

        for url, data_json in seeds_data.items():
            try:
                data = json.loads(data_json)
                data["last_queued"] = now.isoformat()
                pipe.hset(settings.CRAWL_SEEDS_KEY, url, json.dumps(data))
                urls_to_queue.append((url, data.get("priority", 100.0)))

                if force:
                    pipe.srem(settings.CRAWL_SEEN_KEY, url)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue

        pipe.execute()

        # Queue URLs
        queued = 0
        for url, priority in urls_to_queue:
            if force:
                # Direct add since we removed from seen
                self.redis.zadd(settings.CRAWL_QUEUE_KEY, {url: priority})
                queued += 1
            else:
                count = enqueue_batch(
                    self.redis,
                    [url],
                    parent_score=priority,
                    queue_key=settings.CRAWL_QUEUE_KEY,
                    seen_key=settings.CRAWL_SEEN_KEY,
                )
                queued += count

        logger.info(f"Requeued {queued} seeds (force={force})")
        return queued

    def requeue_one(self, url: str, force: bool = False) -> bool:
        """
        Re-add a specific seed to the crawl queue.

        Args:
            url: URL to requeue
            force: If True, remove from crawl:seen first

        Returns:
            True if URL was queued
        """
        data_json = self.redis.hget(settings.CRAWL_SEEDS_KEY, url)
        if not data_json:
            return False

        try:
            data = json.loads(data_json)
            priority = data.get("priority", 100.0)
            data["last_queued"] = datetime.utcnow().isoformat()
            self.redis.hset(settings.CRAWL_SEEDS_KEY, url, json.dumps(data))

            if force:
                self.redis.srem(settings.CRAWL_SEEN_KEY, url)
                self.redis.zadd(settings.CRAWL_QUEUE_KEY, {url: priority})
                return True
            else:
                count = enqueue_batch(
                    self.redis,
                    [url],
                    parent_score=priority,
                    queue_key=settings.CRAWL_QUEUE_KEY,
                    seen_key=settings.CRAWL_SEEN_KEY,
                )
                return count > 0
        except (json.JSONDecodeError, KeyError, ValueError):
            return False
