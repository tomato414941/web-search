"""
Embedding Service - OpenAI embeddings with sync and async support.

Provides both synchronous and asynchronous embedding services.
"""

import logging
import struct
import numpy as np
from openai import OpenAI, AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# text-embedding-3-small has 1536 dimensions
DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_DIMENSIONS = 1536
MAX_CHARS = 30000  # ~7500 tokens, safe limit for 8191 max


def _prepare_text(text: str) -> str:
    """Prepare text for embedding."""
    text = text.replace("\n", " ")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
    return text


def serialize(vector: np.ndarray) -> bytes:
    """Convert numpy array to bytes for storage."""
    return struct.pack(f"{len(vector)}f", *vector)


def deserialize(blob: bytes, dimensions: int = DEFAULT_DIMENSIONS) -> np.ndarray:
    """Convert bytes back to numpy array."""
    expected_size = len(blob) // 4
    if expected_size != dimensions:
        raise ValueError(
            f"Invalid embedding size: expected {dimensions}, got {expected_size}"
        )
    return np.array(struct.unpack(f"{expected_size}f", blob), dtype=np.float32)


class EmbeddingService:
    """Synchronous embedding service using OpenAI."""

    def __init__(self, api_key: str, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self.client = OpenAI(api_key=api_key)
        self.dimensions = DEFAULT_DIMENSIONS

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def _get_embedding(self, text: str) -> list[float]:
        """Call OpenAI API with retry logic."""
        text = _prepare_text(text)
        response = self.client.embeddings.create(input=[text], model=self.model_name)
        return response.data[0].embedding

    def embed(self, text: str) -> bytes:
        """Embed text and return bytes for storage."""
        if not text:
            vector = np.zeros(self.dimensions, dtype=np.float32)
            return serialize(vector)

        try:
            vector_list = self._get_embedding(text)
            vector = np.array(vector_list, dtype=np.float32)
            return serialize(vector)
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

    def embed_query(self, query: str) -> np.ndarray:
        """Embed search query."""
        if not query:
            return np.zeros(self.dimensions, dtype=np.float32)

        vector_list = self._get_embedding(query)
        return np.array(vector_list, dtype=np.float32)

    def deserialize(self, blob: bytes) -> np.ndarray:
        """Convert bytes back to numpy array."""
        return deserialize(blob, self.dimensions)


BATCH_SIZE = 100


class AsyncEmbeddingService:
    """Asynchronous embedding service using OpenAI."""

    def __init__(self, api_key: str, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self.client = AsyncOpenAI(api_key=api_key)
        self.dimensions = DEFAULT_DIMENSIONS

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _get_embedding(self, text: str) -> list[float]:
        """Call OpenAI API with retry logic (async)."""
        text = _prepare_text(text)
        response = await self.client.embeddings.create(
            input=[text], model=self.model_name
        )
        return response.data[0].embedding

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Call OpenAI API with a batch of texts (async)."""
        prepared = [_prepare_text(t) for t in texts]
        response = await self.client.embeddings.create(
            input=prepared, model=self.model_name
        )
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [d.embedding for d in sorted_data]

    async def embed(self, text: str) -> bytes:
        """Embed text and return bytes for storage (async)."""
        if not text:
            vector = np.zeros(self.dimensions, dtype=np.float32)
            return serialize(vector)

        try:
            vector_list = await self._get_embedding(text)
            vector = np.array(vector_list, dtype=np.float32)
            return serialize(vector)
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

    async def embed_batch(self, texts: list[str]) -> list[bytes]:
        """Embed multiple texts in batches and return list of bytes for storage."""
        results: list[bytes] = []
        zero_blob = serialize(np.zeros(self.dimensions, dtype=np.float32))

        # Process in chunks of BATCH_SIZE
        for i in range(0, len(texts), BATCH_SIZE):
            chunk = texts[i : i + BATCH_SIZE]
            non_empty_indices = [j for j, t in enumerate(chunk) if t]
            non_empty_texts = [chunk[j] for j in non_empty_indices]

            chunk_results = [zero_blob] * len(chunk)

            if non_empty_texts:
                try:
                    vectors = await self._get_embeddings_batch(non_empty_texts)
                    for idx, vec_list in zip(non_empty_indices, vectors):
                        vec = np.array(vec_list, dtype=np.float32)
                        chunk_results[idx] = serialize(vec)
                except Exception as e:
                    logger.error("Batch embedding failed for chunk %d: %s", i, e)
                    raise

            results.extend(chunk_results)

        return results

    async def embed_query(self, query: str) -> np.ndarray:
        """Embed search query (async)."""
        if not query:
            return np.zeros(self.dimensions, dtype=np.float32)

        vector_list = await self._get_embedding(query)
        return np.array(vector_list, dtype=np.float32)

    def deserialize(self, blob: bytes) -> np.ndarray:
        """Convert bytes back to numpy array."""
        return deserialize(blob, self.dimensions)
