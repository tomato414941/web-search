"""Embedding generation for the versioned OpenSearch document projection."""

from functools import lru_cache
import math
import os

from openai import OpenAI
from tokenizers import Tokenizer

BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "perplexity/pplx-embed-v1-0.6b"
DIMENSIONS = 1024
TOKENIZER_MODEL = "perplexity-ai/pplx-embed-v1-0.6b"
TOKENIZER_REVISION = "2c4d510dd4a732063c31a0f70193e35067b51fd8"
# Leave one token of headroom within OpenRouter's 32,000-token input limit.
MAX_INPUT_TOKENS = 31_999
MAX_BATCH_TOKENS = 120_000
BATCH_SIZE = 32


@lru_cache(maxsize=1)
def get_tokenizer() -> Tokenizer:
    return Tokenizer.from_pretrained(TOKENIZER_MODEL, revision=TOKENIZER_REVISION)


class Embeddings:
    def __init__(self, client: OpenAI | None = None):
        if client is None:
            api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY is required for embeddings")
            client = OpenAI(
                api_key=api_key,
                base_url=BASE_URL,
                timeout=20,
                max_retries=2,
            )
        self.client = client

    def _prepare_text(self, text: str) -> tuple[str, int]:
        tokenizer = get_tokenizer()
        encoded = tokenizer.encode(text, add_special_tokens=False)
        while len(encoded.ids) > MAX_INPUT_TOKENS:
            # Cut at a character boundary and re-tokenize the actual API input.
            # Decoding a truncated byte-level token sequence can corrupt Unicode.
            text = text[: encoded.offsets[MAX_INPUT_TOKENS][0]]
            encoded = tokenizer.encode(text, add_special_tokens=False)
        return text, len(encoded.ids)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if any(not text.strip() for text in texts):
            raise ValueError("Cannot embed empty text")
        vectors: list[list[float]] = []
        batch: list[str] = []
        batch_tokens = 0
        for text in texts:
            text, tokens = self._prepare_text(text)
            if batch and (
                len(batch) == BATCH_SIZE or batch_tokens + tokens > MAX_BATCH_TOKENS
            ):
                vectors.extend(self._embed_batch(batch))
                batch = []
                batch_tokens = 0
            batch.append(text)
            batch_tokens += tokens
        if batch:
            vectors.extend(self._embed_batch(batch))
        return vectors

    def _embed_batch(self, inputs: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=MODEL,
            input=inputs,
            dimensions=DIMENSIONS,
            encoding_format="float",
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        if [item.index for item in ordered] != list(range(len(inputs))):
            raise RuntimeError("Embedding response does not match input batch")
        vectors: list[list[float]] = []
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
