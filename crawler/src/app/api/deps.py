"""
API Dependencies

Dependency injection for FastAPI routes.
"""

import secrets

from fastapi import Header, HTTPException

from app.db.url_store import UrlStore
from app.services.queue import QueueService
from app.services.seeds import SeedService
from app.core.config import settings

# Lazy-initialized instance
_url_store: UrlStore | None = None


def _get_url_store() -> UrlStore:
    """Get or create UrlStore instance."""
    global _url_store
    if _url_store is None:
        _url_store = UrlStore(
            settings.CRAWLER_DB_PATH,
            recrawl_after_days=settings.CRAWL_RECRAWL_AFTER_DAYS,
        )
    return _url_store


def get_queue_service() -> QueueService:
    """Get queue service instance"""
    return QueueService(_get_url_store())


def get_seed_service() -> SeedService:
    """Get seed service instance"""
    return SeedService(_get_url_store())


def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    """Verify service-to-service API key."""
    if not settings.INDEXER_API_KEY or not secrets.compare_digest(
        x_api_key, settings.INDEXER_API_KEY
    ):
        raise HTTPException(status_code=401, detail="Invalid API key")
