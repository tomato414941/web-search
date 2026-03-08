"""Tests for OpenSearch client and mapping modules."""

from unittest.mock import MagicMock

from shared.opensearch.client import (
    bulk_index,
)


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
