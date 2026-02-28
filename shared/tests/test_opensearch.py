"""Tests for OpenSearch client and mapping modules."""

from unittest.mock import MagicMock

from shared.opensearch.client import (
    INDEX_NAME,
    bulk_index,
    delete_document,
    index_document,
)
from shared.opensearch.mapping import INDEX_SETTINGS, ensure_index


class TestIndexDocument:
    def test_indexes_with_correct_fields(self):
        client = MagicMock()
        index_document(
            client,
            url="https://example.com",
            title_tokens="python プログラミング",
            content_tokens="python は プログラミング 言語",
            word_count=4,
            indexed_at="2026-02-28T00:00:00+00:00",
            authority=0.5,
        )
        client.index.assert_called_once()
        call_kwargs = client.index.call_args
        assert call_kwargs.kwargs["index"] == INDEX_NAME
        assert call_kwargs.kwargs["id"] == "https://example.com"
        body = call_kwargs.kwargs["body"]
        assert body["url"] == "https://example.com"
        assert body["title"] == "python プログラミング"
        assert body["authority"] == 0.5
        assert "embedding" not in body

    def test_includes_embedding_when_provided(self):
        client = MagicMock()
        embedding = [0.1] * 1536
        index_document(
            client,
            url="https://example.com",
            title_tokens="test",
            content_tokens="content",
            word_count=1,
            indexed_at="2026-02-28T00:00:00+00:00",
            embedding=embedding,
        )
        body = client.index.call_args.kwargs["body"]
        assert body["embedding"] == embedding


class TestDeleteDocument:
    def test_deletes_by_url(self):
        client = MagicMock()
        delete_document(client, "https://example.com")
        client.delete.assert_called_once_with(
            index=INDEX_NAME, id="https://example.com", ignore=[404]
        )

    def test_handles_error_gracefully(self):
        client = MagicMock()
        client.delete.side_effect = Exception("connection error")
        delete_document(client, "https://example.com")


class TestBulkIndex:
    def test_returns_zero_for_empty_list(self):
        client = MagicMock()
        assert bulk_index(client, []) == 0
        client.bulk.assert_not_called()

    def test_indexes_multiple_documents(self):
        client = MagicMock()
        client.bulk.return_value = {
            "items": [
                {"index": {"_id": "1", "status": 201}},
                {"index": {"_id": "2", "status": 201}},
            ]
        }
        docs = [
            {"url": "https://a.com", "title": "A", "content": "a"},
            {"url": "https://b.com", "title": "B", "content": "b"},
        ]
        result = bulk_index(client, docs)
        assert result == 2

    def test_counts_errors(self):
        client = MagicMock()
        client.bulk.return_value = {
            "items": [
                {"index": {"_id": "1", "status": 201}},
                {"index": {"_id": "2", "error": {"type": "mapper_parsing_exception"}}},
            ]
        }
        docs = [
            {"url": "https://a.com", "title": "A", "content": "a"},
            {"url": "https://b.com", "title": "B", "content": "b"},
        ]
        result = bulk_index(client, docs)
        assert result == 1


class TestEnsureIndex:
    def test_creates_index_when_not_exists(self):
        client = MagicMock()
        client.indices.exists.return_value = False
        result = ensure_index(client)
        assert result is True
        client.indices.create.assert_called_once_with(
            index=INDEX_NAME, body=INDEX_SETTINGS
        )

    def test_skips_when_exists(self):
        client = MagicMock()
        client.indices.exists.return_value = True
        result = ensure_index(client)
        assert result is False
        client.indices.create.assert_not_called()
