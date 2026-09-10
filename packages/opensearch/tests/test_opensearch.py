"""Tests for OpenSearch client and mapping modules."""

from unittest.mock import MagicMock

from web_search_opensearch.client import (
    bulk_index,
)
from web_search_opensearch.document import SearchIndexDocument
from web_search_opensearch.mapping import INDEX_SETTINGS, ensure_index


def test_search_index_document_contract_matches_mapping():
    assert set(SearchIndexDocument.__annotations__) == set(
        INDEX_SETTINGS["mappings"]["properties"]
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
            {
                "url": "https://a.com",
                "title": "A",
                "content": "a",
                "title_terms": "a",
                "content_terms": "a",
                "embedding": [1.0],
                "host": "a.com",
                "path": "/",
            },
            {
                "url": "https://b.com",
                "title": "B",
                "content": "b",
                "title_terms": "b",
                "content_terms": "b",
                "embedding": [1.0],
                "host": "b.com",
                "path": "/",
            },
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
            {
                "url": "https://a.com",
                "title": "A",
                "content": "a",
                "title_terms": "a",
                "content_terms": "a",
                "embedding": [1.0],
                "host": "a.com",
                "path": "/",
            },
            {
                "url": "https://b.com",
                "title": "B",
                "content": "b",
                "title_terms": "b",
                "content_terms": "b",
                "embedding": [1.0],
                "host": "b.com",
                "path": "/",
            },
        ]
        result = bulk_index(client, docs)
        assert result == 1


def test_old_index_is_rejected_without_mapping_mutation():
    import pytest

    client = MagicMock()
    client.indices.exists.return_value = True
    client.indices.get_mapping.return_value = {"old": {"mappings": {"properties": {}}}}
    with pytest.raises(RuntimeError, match="rebuild"):
        ensure_index(client)
    client.indices.put_mapping.assert_not_called()
    client.transport.perform_request.assert_not_called()


def test_ensure_index_creates_native_pipeline_and_target_index():
    from web_search_opensearch.mapping import SEARCH_PIPELINE, PIPELINE_SETTINGS

    client = MagicMock()
    client.indices.exists.return_value = False
    assert ensure_index(client, target_index="hybrid-test") is True
    client.indices.create.assert_called_once_with(
        index="hybrid-test", body=INDEX_SETTINGS
    )
    client.transport.perform_request.assert_called_once_with(
        "PUT",
        f"/_search/pipeline/{SEARCH_PIPELINE}",
        body=PIPELINE_SETTINGS,
    )
