from web_search_frontend.core.config import settings


def get_indexed_document_count() -> int:
    from web_search_opensearch.client import INDEX_NAME, get_client

    client = get_client(settings.OPENSEARCH_URL)
    return int(client.count(index=INDEX_NAME)["count"])
