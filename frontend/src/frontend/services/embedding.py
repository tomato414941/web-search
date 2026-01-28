"""
Embedding Service - Frontend-specific instance.

Uses the shared EmbeddingService with frontend configuration.
"""

from frontend.core.config import settings
from shared.embedding import EmbeddingService

# Global instance using frontend config
embedding_service = EmbeddingService(api_key=settings.OPENAI_API_KEY)
