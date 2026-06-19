from unittest.mock import MagicMock

from web_search_opensearch.client import INDEX_NAME, bulk_index, doc_id, index_document


def test_index_document_accepts_search_document_fields():
    client = MagicMock()
    document = {
        "url": "https://example.com/page",
        "title": "example title",
        "content": "example content",
        "title_terms": "example title",
        "content_terms": "example content",
        "page_rank": 0.5,
        "domain_rank": 0.25,
        "host": "example.com",
        "path": "/page",
    }

    index_document(client, document)

    client.index.assert_called_once_with(
        index=INDEX_NAME,
        id=doc_id("https://example.com/page"),
        body=document,
    )


def test_bulk_index_accepts_target_index():
    client = MagicMock()
    client.bulk.return_value = {"items": [{"index": {}}]}
    document = {
        "url": "https://example.com/page",
        "title": "example title",
        "content": "example content",
        "title_terms": "example title",
        "content_terms": "example content",
        "page_rank": 0.5,
        "domain_rank": 0.25,
        "host": "example.com",
        "path": "/page",
    }

    indexed = bulk_index(client, [document], target_index="documents_v2")

    assert indexed == 1
    client.bulk.assert_called_once_with(
        body=[
            {
                "index": {
                    "_index": "documents_v2",
                    "_id": "https://example.com/page",
                }
            },
            document,
        ]
    )
