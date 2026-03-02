"""OpenSearch index mapping and management."""

import logging

from opensearchpy import OpenSearch

from shared.opensearch.client import INDEX_NAME

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
        "index.knn": True,
    },
    "mappings": {
        "properties": {
            "url": {"type": "keyword"},
            "title": {
                "type": "text",
                "analyzer": "sudachi_whitespace",
                "similarity": "custom_bm25",
            },
            "content": {
                "type": "text",
                "analyzer": "sudachi_whitespace",
                "similarity": "custom_bm25",
            },
            "word_count": {"type": "integer"},
            "indexed_at": {"type": "date"},
            "published_at": {"type": "date"},
            "authority": {"type": "float"},
            "content_quality": {"type": "float"},
            "embedding": {
                "type": "knn_vector",
                "dimension": 1536,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "lucene",
                },
            },
        }
    },
}


def ensure_index(client: OpenSearch) -> bool:
    """Create the documents index if it doesn't exist.

    Returns:
        True if index was created, False if it already existed.
    """
    if client.indices.exists(index=INDEX_NAME):
        logger.info("OpenSearch index '%s' already exists", INDEX_NAME)
        return False

    client.indices.create(index=INDEX_NAME, body=INDEX_SETTINGS)
    logger.info("Created OpenSearch index '%s'", INDEX_NAME)
    return True
