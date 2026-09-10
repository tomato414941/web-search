import json

import httpx
from openai import OpenAI
import pytest

from web_search_opensearch.embeddings import (
    Embeddings,
    DIMENSIONS,
    MAX_INPUT_TOKENS,
    BATCH_SIZE,
    MODEL,
)


def test_batches_respect_token_limits_and_restore_response_order():
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": MODEL,
                "data": [
                    {
                        "object": "embedding",
                        "index": i,
                        "embedding": [float(i + 1)] + [0.0] * (DIMENSIONS - 1),
                    }
                    for i in reversed(range(len(payload["input"])))
                ],
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )

    with OpenAI(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    ) as client:
        vectors = Embeddings(client).embed(
            ["日本語の長い文章です。" * 3000] * (BATCH_SIZE + 1)
        )
    assert [len(payload["input"]) for payload in requests] == [BATCH_SIZE, 1]
    for payload in requests:
        assert payload["model"] == MODEL
        assert payload["dimensions"] == DIMENSIONS
        assert sum(map(len, payload["input"])) < 300_000
        assert all(len(tokens) == MAX_INPUT_TOKENS for tokens in payload["input"])
    assert len(vectors) == BATCH_SIZE + 1
    assert [row[0] for row in vectors[:BATCH_SIZE]] == list(range(1, BATCH_SIZE + 1))


@pytest.mark.parametrize(
    "data",
    [
        [],
        [{"index": 0, "embedding": [1.0]}],
        [{"index": 1, "embedding": [1.0] * DIMENSIONS}],
        [{"index": 0, "embedding": [0.0] * DIMENSIONS}],
    ],
)
def test_invalid_embedding_response_is_rejected(data):
    def respond(request):
        return httpx.Response(
            200,
            json={
                "data": data,
                "model": MODEL,
                "object": "list",
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )

    with OpenAI(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    ) as client:
        with pytest.raises(RuntimeError):
            Embeddings(client).query("test")


def test_empty_text_does_not_call_provider():
    def unexpected(request):
        raise AssertionError("Empty input must not reach the provider")

    with OpenAI(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(unexpected)),
    ) as client:
        with pytest.raises(ValueError):
            Embeddings(client).query("")
