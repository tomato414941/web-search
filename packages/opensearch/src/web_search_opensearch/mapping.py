"""OpenSearch index mapping and management."""

import logging

from opensearchpy import OpenSearch

from web_search_opensearch.client import index_name
from web_search_opensearch.embeddings import (
    DIMENSIONS,
    MODEL,
    MAX_INPUT_TOKENS,
    TOKENIZER_REVISION,
)

logger = logging.getLogger(__name__)

SEARCH_PIPELINE = "web-search-hybrid-rrf"
SCHEMA = {
    "search_schema": "hybrid-v2",
    "embedding_model": MODEL,
    "tokenizer_revision": TOKENIZER_REVISION,
    "max_input_tokens": MAX_INPUT_TOKENS,
}
PIPELINE_SETTINGS = {
    "phase_results_processors": [
        {"score-ranker-processor": {"combination": {"technique": "rrf"}}}
    ]
}

INDEX_SETTINGS = {
    "settings": {
        "number_of_shards": 1,
        "index.knn": True,
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
        "_meta": SCHEMA,
        "dynamic": "strict",
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
            "embedding": {
                "type": "knn_vector",
                "dimension": DIMENSIONS,
                "method": {
                    "name": "hnsw",
                    "engine": "lucene",
                    "space_type": "cosinesimil",
                    "parameters": {},
                },
            },
        },
    },
}


def validate_index(client: OpenSearch, *, target_index: str | None = None) -> None:
    """Reject old or mismatched projections; never patch an existing schema."""
    resolved = index_name(target_index)
    mappings = client.indices.get_mapping(index=resolved)
    if len(mappings) != 1:
        raise RuntimeError("Search must resolve to exactly one hybrid index")
    mapping = next(iter(mappings.values()))["mappings"]
    if (
        mapping.get("_meta") != SCHEMA
        or mapping.get("properties") != INDEX_SETTINGS["mappings"]["properties"]
        or mapping.get("dynamic") != "strict"
    ):
        raise RuntimeError(
            "Search index schema mismatch; rebuild into a new hybrid index"
        )
    settings = client.indices.get_settings(index=resolved)
    if any(
        str(value["settings"]["index"].get("knn")).lower() != "true"
        for value in settings.values()
    ):
        raise RuntimeError("Hybrid search requires index.knn=true")


def ensure_index(client: OpenSearch, *, target_index: str | None = None) -> bool:
    """Provision the native search pipeline and create or validate its index."""
    resolved = index_name(target_index)
    created = not client.indices.exists(index=resolved)
    if created:
        client.indices.create(index=resolved, body=INDEX_SETTINGS)
    else:
        validate_index(client, target_index=resolved)
    client.transport.perform_request(
        "PUT",
        f"/_search/pipeline/{SEARCH_PIPELINE}",
        body=PIPELINE_SETTINGS,
    )
    return created
