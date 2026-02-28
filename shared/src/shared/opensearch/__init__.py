from shared.opensearch.client import get_client, index_document, delete_document
from shared.opensearch.mapping import ensure_index

__all__ = ["get_client", "index_document", "delete_document", "ensure_index"]
