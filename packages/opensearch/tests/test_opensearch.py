"""Tests for OpenSearch client and mapping modules."""

from unittest.mock import MagicMock

from web_search_opensearch.client import (
    bulk_index,
)
from web_search_opensearch.document import SearchIndexDocument
from web_search_opensearch.mapping import INDEX_SETTINGS, ensure_index
from web_search_opensearch.search import (
    HostPathBoosts,
    RetrievalBoosts,
    SubjectPhraseBoosts,
    _build_bm25_bool_query,
)


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
                "page_rank": 0.0,
                "domain_rank": 0.0,
                "host": "a.com",
                "path": "/",
            },
            {
                "url": "https://b.com",
                "title": "B",
                "content": "b",
                "title_terms": "b",
                "content_terms": "b",
                "page_rank": 0.0,
                "domain_rank": 0.0,
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
                "page_rank": 0.0,
                "domain_rank": 0.0,
                "host": "a.com",
                "path": "/",
            },
            {
                "url": "https://b.com",
                "title": "B",
                "content": "b",
                "title_terms": "b",
                "content_terms": "b",
                "page_rank": 0.0,
                "domain_rank": 0.0,
                "host": "b.com",
                "path": "/",
            },
        ]
        result = bulk_index(client, docs)
        assert result == 1


def test_ensure_index_updates_missing_mappings():
    client = MagicMock()
    client.indices.exists.return_value = True
    existing = {
        field: schema
        for field, schema in INDEX_SETTINGS["mappings"]["properties"].items()
        if field not in {"host", "path"}
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
            }
        },
    )


def test_ensure_index_creates_target_index():
    client = MagicMock()
    client.indices.exists.return_value = False

    created = ensure_index(client, target_index="documents_v2")

    assert created is True
    client.indices.create.assert_called_once_with(
        index="documents_v2",
        body=INDEX_SETTINGS,
    )


def test_build_bm25_bool_query_adds_canonical_retrieval_signals():
    query = _build_bm25_bool_query(
        "github",
        required_domains=("docs.github.com",),
        retrieval_boosts=RetrievalBoosts(
            host_path=HostPathBoosts(
                hosts=("github.com",),
                paths=("/", "/docs"),
                host_boost=3.0,
                exact_path_boost=5.0,
                path_prefix_boost=4.0,
                homepage_boost=6.0,
            )
        ),
    )

    should = query["bool"]["should"]
    filters = query["bool"]["filter"]

    assert {"term": {"host": {"value": "github.com", "boost": 3.0}}} in should
    assert {"term": {"host": {"value": "www.github.com", "boost": 3.0}}} in should
    assert {"term": {"path": {"value": "/", "boost": 6.0}}} in should
    assert {"term": {"path": {"value": "/docs", "boost": 5.0}}} in should
    assert {"prefix": {"path": {"value": "/docs", "boost": 4.0}}} in should
    assert {
        "bool": {
            "should": [
                {"term": {"host": {"value": "docs.github.com"}}},
                {"term": {"host": {"value": "www.docs.github.com"}}},
                {"prefix": {"url": {"value": "https://docs.github.com/"}}},
                {"prefix": {"url": {"value": "http://docs.github.com/"}}},
                {"prefix": {"url": {"value": "https://www.docs.github.com/"}}},
                {"prefix": {"url": {"value": "http://www.docs.github.com/"}}},
            ],
            "minimum_should_match": 1,
        }
    } in filters


def test_build_bm25_bool_query_uses_minimum_should_match():
    query = _build_bm25_bool_query("docker compose orphan containers")

    text_clause = query["bool"]["must"][0]["multi_match"]

    assert text_clause["operator"] == "or"
    assert text_clause["minimum_should_match"] == "60%"


def test_build_bm25_bool_query_adds_comparison_retrieval_signals():
    query = _build_bm25_bool_query(
        "fastapi vs django",
        retrieval_boosts=RetrievalBoosts(
            subject_phrase=SubjectPhraseBoosts(
                subjects=("fastapi", "django"),
                subjects_boost=4.0,
                title_boost=6.0,
                phrase_boost=7.0,
                cue_boost=3.0,
            )
        ),
    )

    should = query["bool"]["should"]

    assert {
        "multi_match": {
            "query": "fastapi django",
            "fields": ["title_terms^6", "content_terms"],
            "type": "cross_fields",
            "operator": "and",
            "boost": 6.0,
        }
    } in should
    assert {
        "multi_match": {
            "query": "fastapi django vs versus compare comparison",
            "fields": ["title_terms^4"],
            "type": "cross_fields",
            "operator": "or",
            "minimum_should_match": "50%",
            "boost": 3.0,
        }
    } in should
    assert {
        "multi_match": {
            "query": "fastapi vs django",
            "fields": ["title_terms^3", "content_terms"],
            "type": "phrase",
            "boost": 7.0,
        }
    } in should
    assert not any("wildcard" in clause for clause in should)


def test_build_bm25_bool_query_omits_comparison_signals_by_default():
    query = _build_bm25_bool_query("fastapi vs django")

    assert "should" not in query["bool"]
