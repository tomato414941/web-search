"""
API Dependencies

Dependency injection for FastAPI routes.
"""

from app.db import Frontier, History
from app.services.queue import QueueService
from app.services.seeds import SeedService
from app.core.config import settings

# Lazy-initialized instances
_frontier: Frontier | None = None
_history: History | None = None


def _get_frontier() -> Frontier:
    """Get or create Frontier instance."""
    global _frontier
    if _frontier is None:
        _frontier = Frontier(settings.CRAWLER_DB_PATH)
    return _frontier


def _get_history() -> History:
    """Get or create History instance."""
    global _history
    if _history is None:
        _history = History(
            settings.CRAWLER_DB_PATH,
            recrawl_after_days=settings.CRAWL_RECRAWL_AFTER_DAYS,
        )
    return _history


def get_queue_service() -> QueueService:
    """Get queue service instance"""
    return QueueService(_get_frontier(), _get_history())


def get_seed_service() -> SeedService:
    """Get seed service instance"""
    return SeedService(_get_frontier(), _get_history())
