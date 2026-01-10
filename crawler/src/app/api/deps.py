"""
API Dependencies

Dependency injection for FastAPI routes.
"""

from shared.db.redis import get_redis
from app.services.queue import QueueService


def get_queue_service() -> QueueService:
    """Get queue service instance"""
    redis_client = get_redis()
    return QueueService(redis_client)
