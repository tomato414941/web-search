from web_search_frontend.core.config import settings


def get_indexed_document_count() -> int:
    from web_search_opensearch.client import get_client, index_name

    client = get_client(settings.OPENSEARCH_URL)
    return int(client.count(index=index_name())["count"])
