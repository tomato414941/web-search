"""Embedding generation for the versioned OpenSearch document projection."""

from functools import lru_cache
import math

from openai import OpenAI
import tiktoken

MODEL = "text-embedding-3-small"
DIMENSIONS = 1536
MAX_INPUT_TOKENS = 8191
# Bound each request below the API's 300,000-token aggregate limit.
BATCH_SIZE = 32


class Embeddings:
    def __init__(self, client: OpenAI | None = None):
        self.client = (
            client if client is not None else OpenAI(timeout=20, max_retries=2)
        )
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            inputs = [
                self.encoding.encode(text, disallowed_special=())[:MAX_INPUT_TOKENS]
                for text in texts[start : start + BATCH_SIZE]
            ]
            if any(not tokens for tokens in inputs):
                raise ValueError("Cannot embed empty text")
            response = self.client.embeddings.create(
                model=MODEL,
                input=inputs,
                dimensions=DIMENSIONS,
                encoding_format="float",
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            if [item.index for item in ordered] != list(range(len(inputs))):
                raise RuntimeError("Embedding response does not match input batch")
            for item in ordered:
                vector = item.embedding
                if (
                    len(vector) != DIMENSIONS
                    or not all(math.isfinite(value) for value in vector)
                    or not any(vector)
                ):
                    raise RuntimeError("Embedding response contains an invalid vector")
                vectors.append(vector)
        return vectors

    def query(self, text: str) -> list[float]:
        return self.embed([text])[0]


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    return Embeddings()
