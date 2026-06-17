from unittest.mock import MagicMock

from web_search_opensearch.client import INDEX_NAME, doc_id, index_document


def test_index_document_accepts_search_document_fields():
    client = MagicMock()

    index_document(
        client,
        url="https://example.com/page",
        title="example title",
        content="example content",
        indexed_at="2026-06-17T00:00:00+00:00",
        page_rank=0.5,
        domain_rank=0.25,
        host="example.com",
        path="/page",
        is_homepage=False,
    )

    client.index.assert_called_once_with(
        index=INDEX_NAME,
        id=doc_id("https://example.com/page"),
        body={
            "url": "https://example.com/page",
            "title": "example title",
            "content": "example content",
            "indexed_at": "2026-06-17T00:00:00+00:00",
            "page_rank": 0.5,
            "domain_rank": 0.25,
            "host": "example.com",
            "path": "/page",
            "is_homepage": False,
        },
    )
