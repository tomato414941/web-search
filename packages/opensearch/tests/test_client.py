from unittest.mock import MagicMock

from web_search_opensearch.client import INDEX_NAME, doc_id, index_document


def test_index_document_accepts_search_document_fields():
    client = MagicMock()
    document = {
        "url": "https://example.com/page",
        "title": "example title",
        "content": "example content",
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
