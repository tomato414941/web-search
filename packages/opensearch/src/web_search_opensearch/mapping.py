"""OpenSearch index mapping and management."""

import logging

from opensearchpy import OpenSearch

from web_search_opensearch.client import index_name

logger = logging.getLogger(__name__)

INDEX_SETTINGS = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "sudachi_whitespace": {
                    "type": "custom",
                    "tokenizer": "whitespace",
                    "filter": ["lowercase"],
                }
            }
        },
        "similarity": {
            "custom_bm25": {
                "type": "BM25",
                "k1": 1.2,
                "b": 0.75,
            }
        },
    },
    "mappings": {
        "properties": {
            "url": {"type": "keyword"},
            "host": {"type": "keyword"},
            "path": {"type": "keyword"},
            "title": {
                "type": "text",
                "index": False,
            },
            "content": {
                "type": "text",
                "index": False,
            },
            "title_terms": {
                "type": "text",
                "analyzer": "sudachi_whitespace",
                "similarity": "custom_bm25",
            },
            "content_terms": {
                "type": "text",
                "analyzer": "sudachi_whitespace",
                "similarity": "custom_bm25",
            },
            "page_rank": {"type": "float"},
            "domain_rank": {"type": "float"},
        }
    },
}


def _missing_properties(client: OpenSearch, *, target_index: str) -> dict[str, object]:
    response = client.indices.get_mapping(index=target_index)
    mapping = response.get(target_index)
    if mapping is None and response:
        mapping = next(iter(response.values()))
    properties = (mapping or {}).get("mappings", {}).get("properties", {})
    expected = INDEX_SETTINGS["mappings"]["properties"]
    return {
        field: schema for field, schema in expected.items() if field not in properties
    }


def ensure_index(client: OpenSearch, *, target_index: str | None = None) -> bool:
    """Create the documents index if it doesn't exist.

    Returns:
        True if index was created, False if it already existed.
    """
    resolved_index = index_name(target_index)
    if client.indices.exists(index=resolved_index):
        missing = _missing_properties(client, target_index=resolved_index)
        if missing:
            client.indices.put_mapping(
                index=resolved_index, body={"properties": missing}
            )
            logger.info(
                "Updated OpenSearch index '%s' with fields: %s",
                resolved_index,
                ", ".join(sorted(missing)),
            )
        logger.info("OpenSearch index '%s' already exists", resolved_index)
        return False

    client.indices.create(index=resolved_index, body=INDEX_SETTINGS)
    logger.info("Created OpenSearch index '%s'", resolved_index)
    return True
