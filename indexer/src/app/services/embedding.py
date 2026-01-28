"""
Embedding Service - Indexer-specific async instance.

Uses the shared AsyncEmbeddingService with indexer configuration.
"""

from app.core.config import settings
from shared.embedding import AsyncEmbeddingService

# Global async instance using indexer config
embedding_service = AsyncEmbeddingService(api_key=settings.OPENAI_API_KEY)
