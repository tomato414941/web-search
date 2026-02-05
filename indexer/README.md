# Indexer Service

The Indexer Service is a write-optimized microservice responsible for ingesting, processing, and storing web pages.

## Responsibilities

1.  **Ingestion**: Receives crawled data (URL, Title, Content) from the Crawler Service via HTTP API.
2.  **Tokenization**: Uses `shared.analyzer` (SudachiPy) to tokenize Japanese text for the custom inverted index.
3.  **Embedding**: Uses OpenAI API to generate vector embeddings for semantic search.
4.  **Storage**: Writes data to the shared DB (`shared.db.search`) using PostgreSQL (production) or SQLite (local dev).

## Directory Structure

```
indexer/
├── Dockerfile         # Docker build instruction
├── requirements.txt   # Dependencies (FastAPI, SudachiPy, OpenAI)
├── src/
│   └── app/
│       ├── api/       # API Routes (/api/v1/indexer/*)
│       ├── core/      # Config
│       ├── services/  # Business Logic (IndexerService, EmbeddingService)
│       └── main.py    # Entry Point
└── tests/             # API Tests
```

## Running Locally

```bash
# Install dependencies
pip install -e ../shared
pip install -r requirements.txt

# Start Server
uvicorn app.main:app --reload --port 8081
```

## API Endpoints

*   `POST /api/v1/indexer/page`: Submit a page for indexing.
*   `GET /health`: Health check (recommended).
*   `GET /api/v1/health`: Health check (backward compatible).
