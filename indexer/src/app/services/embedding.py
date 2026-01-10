"""Async Embedding Service using OpenAI API."""

import logging
import pickle
import numpy as np
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Async embedding service using OpenAI text-embedding-3-small."""

    def __init__(self, model_name: str = "text-embedding-3-small"):
        self.model_name = model_name
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        # Dimensions for text-embedding-3-small is 1536 by default
        self.dimensions = 1536

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _get_embedding(self, text: str) -> list[float]:
        """Call OpenAI API with retry logic (async)."""
        text = text.replace("\n", " ")  # Recommended for OpenAI embeddings
        # Safety Truncation: 1 token ~ 4 chars. Limit to ~8000 tokens (text-embedding-3-small max is 8191).
        # We use a hard char limit of 30000 chars (approx 7500 tokens) to be safe and save memory.
        if len(text) > 30000:
            text = text[:30000]

        response = await self.client.embeddings.create(input=[text], model=self.model_name)
        return response.data[0].embedding

    async def embed(self, text: str) -> bytes:
        """Embed text and return bytes for storage (async)."""
        if not text:
            # Return zero vector
            return pickle.dumps(np.zeros(self.dimensions, dtype=np.float32))

        try:
            vector_list = await self._get_embedding(text)
            vector = np.array(vector_list, dtype=np.float32)
            # Serialize numpy array to bytes
            return pickle.dumps(vector)
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise e

    def deserialize(self, blob: bytes) -> np.ndarray:
        """Convert bytes back to numpy array."""
        return pickle.loads(blob)

    async def embed_query(self, query: str) -> np.ndarray:
        """Embed search query (async)."""
        if not query:
            return np.zeros(self.dimensions, dtype=np.float32)

        vector_list = await self._get_embedding(query)
        return np.array(vector_list, dtype=np.float32)


# Global instance
embedding_service = EmbeddingService()
