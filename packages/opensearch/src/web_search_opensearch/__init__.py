from web_search_opensearch.client import (
    doc_id,
    get_client,
    index_document,
    delete_document,
)
from web_search_opensearch.mapping import ensure_index

__all__ = ["doc_id", "get_client", "index_document", "delete_document", "ensure_index"]
