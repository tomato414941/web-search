import json

import httpx
from openai import OpenAI
import pytest

from web_search_opensearch.embeddings import (
    BASE_URL,
    Embeddings,
    DIMENSIONS,
    MAX_INPUT_TOKENS,
    MAX_BATCH_TOKENS,
    BATCH_SIZE,
    MODEL,
    get_tokenizer,
)


@pytest.fixture
def recorded_embeddings():
    requests = []

    def respond(request):
        assert str(request.url) == f"{BASE_URL}/embeddings"
        assert request.headers["Authorization"] == "Bearer test-key"
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
        base_url=BASE_URL,
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    ) as client:
        yield Embeddings(client), requests


def test_batches_send_text_and_restore_response_order(recorded_embeddings):
    embeddings, requests = recorded_embeddings
    texts = [f"日本語と English の文書 {i}" for i in range(BATCH_SIZE + 1)]
    vectors = embeddings.embed(texts)
    assert [len(payload["input"]) for payload in requests] == [BATCH_SIZE, 1]
    assert [text for payload in requests for text in payload["input"]] == texts
    for payload in requests:
        assert payload["model"] == MODEL
        assert payload["dimensions"] == DIMENSIONS
        assert payload["encoding_format"] == "float"
    assert len(vectors) == BATCH_SIZE + 1
    assert [row[0] for row in vectors[:BATCH_SIZE]] == list(range(1, BATCH_SIZE + 1))


def test_long_inputs_respect_per_text_and_aggregate_limits(recorded_embeddings):
    embeddings, requests = recorded_embeddings
    text = "日本語の長い文章です。" * 5000
    assert len(get_tokenizer().encode(text).ids) > MAX_INPUT_TOKENS
    assert len(embeddings.embed([text] * 4)) == 4
    assert len(requests) > 1
    for payload in requests:
        counts = [
            len(get_tokenizer().encode(value, add_special_tokens=False).ids)
            for value in payload["input"]
        ]
        assert all(0 < count <= MAX_INPUT_TOKENS for count in counts)
        assert sum(counts) <= MAX_BATCH_TOKENS
        assert all(text.startswith(value) for value in payload["input"])


def test_truncation_preserves_unicode_and_literal_special_tokens(
    recorded_embeddings, monkeypatch
):
    from web_search_opensearch import embeddings as module

    embeddings, requests = recorded_embeddings
    monkeypatch.setattr(module, "MAX_INPUT_TOKENS", 7)
    text = "<|endoftext|>日本語🧑🏽‍💻𠮷野家" * 10
    embeddings.query(text)
    actual = requests[0]["input"][0]
    assert actual.startswith("<|endoftext|>")
    assert text.startswith(actual)
    assert "\ufffd" not in actual
    assert len(get_tokenizer().encode(actual, add_special_tokens=False).ids) <= 7


def test_default_client_uses_openrouter_key_and_url(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-openai-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://unrelated.example/v1")
    embeddings = Embeddings()
    try:
        assert str(embeddings.client.base_url) == f"{BASE_URL}/"
        assert embeddings.client.api_key == "test-openrouter-key"
    finally:
        embeddings.client.close()


def test_missing_openrouter_key_does_not_use_openai_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-openai-key")
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        Embeddings()


@pytest.mark.parametrize(
    "data",
    [
        [],
        [{"index": 0, "embedding": [1.0]}],
        [{"index": 1, "embedding": [1.0] * DIMENSIONS}],
        [{"index": 0, "embedding": [0.0] * DIMENSIONS}],
        [
            {"index": 0, "embedding": [1.0] * DIMENSIONS},
            {"index": 0, "embedding": [1.0] * DIMENSIONS},
        ],
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


@pytest.mark.parametrize("texts", [[""], [" \n\t"], ["valid text", ""]])
def test_empty_text_does_not_call_provider(texts):
    def unexpected(request):
        raise AssertionError("Empty input must not reach the provider")

    with OpenAI(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(unexpected)),
    ) as client:
        with pytest.raises(ValueError):
            Embeddings(client).embed(texts)


def test_empty_batch_does_not_call_provider(recorded_embeddings):
    embeddings, requests = recorded_embeddings
    assert embeddings.embed([]) == []
    assert requests == []
