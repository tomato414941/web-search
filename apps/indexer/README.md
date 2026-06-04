# Indexer Service

The Indexer Service is a write-optimized microservice responsible for ingesting, processing, and storing web pages.

This document is intentionally service-specific.
For project-wide product goals and system structure, start with:

- `../../README.md`
- `../../docs/architecture.md`

## Responsibilities

1.  **Ingestion**: Receives crawled data (URL, Title, Content) from the Crawler Service via HTTP API and queues async jobs.
2.  **Tokenization**: Uses `web_search_kernel.analyzer` (SudachiPy) to tokenize Japanese text for the custom inverted index.
3.  **Storage**: Writes data through `web_search_indexer.services.document_indexer` and `web_search_postgres.search` into PostgreSQL.
4.  **Baseline-only indexing**: the API and worker path handle metadata, scoring, and OpenSearch sync. Experimental embeddings live in `packages/indexing`, not in the indexer package.

## Directory Structure

```
apps/indexer/
├── Dockerfile         # Docker build instruction
├── pyproject.toml     # Workspace package metadata
├── src/
│   └── web_search_indexer/
│       ├── api/       # API Routes
│       ├── core/      # Config
│       ├── services/  # Business Logic (IndexerService)
│       └── main.py    # Entry Point
└── tests/             # API Tests
```

## Running Locally

```bash
make sync-indexer

# Start Server
uv run --package web-search-indexer uvicorn web_search_indexer.main:app --reload --port 8081
uv run --package web-search-indexer web-search-calc-pagerank
uv run --package web-search-indexer web-search-inject-dummy-data
uv run --package web-search-indexer web-search-verify-opensearch
uv run --package web-search-indexer web-search-backfill-factual-density
uv run --package web-search-indexer web-search-backfill-opensearch
uv run --package web-search-indexer web-search-backfill-temporal-anchor
```

## API Endpoints

*   `POST /indexing-jobs`: Queue a page for asynchronous indexing (`202 Accepted` + `job_id`).
*   `GET /health`: Health check.
