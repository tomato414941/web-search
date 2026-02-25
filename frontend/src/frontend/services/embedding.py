"""Embedding Service - Cached query embedding for hybrid search."""

import logging
import threading

import numpy as np
from cachetools import TTLCache

from frontend.core.config import settings
from shared.embedding import EmbeddingService, deserialize

logger = logging.getLogger(__name__)

_QUERY_CACHE_MAX = 10_000
_QUERY_CACHE_TTL = 3600  # 1 hour

_embedding_service: EmbeddingService | None = None
_query_cache: TTLCache[str, np.ndarray] = TTLCache(
    maxsize=_QUERY_CACHE_MAX, ttl=_QUERY_CACHE_TTL
)
_cache_lock = threading.Lock()

if settings.OPENAI_API_KEY:
    try:
        _embedding_service = EmbeddingService(api_key=settings.OPENAI_API_KEY)
        logger.info("EmbeddingService initialized (hybrid search available)")
    except Exception:
        logger.warning("Failed to initialize EmbeddingService, falling back to BM25")


def cached_embed_query(query: str) -> np.ndarray:
    """Embed query with TTL cache. Raises if embedding service unavailable."""
    with _cache_lock:
        cached = _query_cache.get(query)
        if cached is not None:
            return cached
    if _embedding_service is None:
        raise RuntimeError("EmbeddingService not available")
    result = _embedding_service.embed_query(query)
    with _cache_lock:
        _query_cache[query] = result
    return result


embed_query_func = cached_embed_query if _embedding_service else None
deserialize_func = deserialize if _embedding_service else None
