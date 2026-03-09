"""Tests for OpenSearch client and mapping modules."""

from unittest.mock import MagicMock

from shared.opensearch.client import (
    bulk_index,
)
from shared.opensearch.mapping import INDEX_SETTINGS, ensure_index
from shared.opensearch.search import _build_bm25_bool_query


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


def test_ensure_index_updates_missing_mappings():
    client = MagicMock()
    client.indices.exists.return_value = True
    existing = {
        field: schema
        for field, schema in INDEX_SETTINGS["mappings"]["properties"].items()
        if field not in {"host", "path", "is_homepage"}
    }
    client.indices.get_mapping.return_value = {
        "documents": {"mappings": {"properties": existing}}
    }

    created = ensure_index(client)

    assert created is False
    client.indices.put_mapping.assert_called_once_with(
        index="documents",
        body={
            "properties": {
                "host": {"type": "keyword"},
                "path": {"type": "keyword"},
                "is_homepage": {"type": "boolean"},
            }
        },
    )


def test_build_bm25_bool_query_adds_canonical_retrieval_signals():
    query = _build_bm25_bool_query(
        "github",
        canonical_domains=("github.com",),
        canonical_paths=("/", "/docs"),
    )

    should = query["bool"]["should"]

    assert {"term": {"host": {"value": "github.com", "boost": 3.0}}} in should
    assert {"term": {"host": {"value": "www.github.com", "boost": 3.0}}} in should
    assert {"term": {"is_homepage": {"value": True, "boost": 6.0}}} in should
    assert {"prefix": {"path": {"value": "/docs", "boost": 4.0}}} in should
