from unittest.mock import patch


def test_search_index_returns_indexed_document_total(client):
    with patch(
        "web_search_frontend.api.routers.search_index.get_indexed_document_count",
        return_value=123,
    ):
        response = client.get("/indexed-documents")

    assert response.status_code == 200
    assert response.json() == {"documents": {"total": 123}}
