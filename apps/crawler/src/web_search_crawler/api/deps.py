"""
API Dependencies

Dependency injection for FastAPI routes.
"""

import secrets

from fastapi import Header, HTTPException

from web_search_crawler.core.config import settings


def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    """Verify service-to-service API key."""
    if not settings.INDEXER_API_KEY or not secrets.compare_digest(
        x_api_key, settings.INDEXER_API_KEY
    ):
        raise HTTPException(status_code=401, detail="Invalid API key")
