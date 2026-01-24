"""
API Dependencies

Dependency injection for FastAPI routes.
"""

from shared.db.redis import get_redis
from app.services.queue import QueueService
from app.services.seeds import SeedService


def get_queue_service() -> QueueService:
    """Get queue service instance"""
    redis_client = get_redis()
    return QueueService(redis_client)


def get_seed_service() -> SeedService:
    """Get seed service instance"""
    redis_client = get_redis()
    return SeedService(redis_client)
