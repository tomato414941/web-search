# PaleBlueSearch

**Web Search API for AI Agents** — Search the web with freshness metadata that AI can trust.

A full-stack search engine with its own crawler, BM25 + vector hybrid ranking,
and Japanese NLP support. Every search hit includes `indexed_at` and `published_at`
timestamps so AI consumers know exactly how fresh the information is.

## Features

- **Freshness Metadata**: Every hit returns `indexed_at` (crawl time) and `published_at` (original publication date) — built for AI agents that need to know when information was created.
- **Hybrid Search**: BM25 keyword matching + vector semantic search with RRF fusion.
- **600K+ Indexed Pages**: Own crawler with PageRank, domain diversity, and robots.txt compliance.
- **Japanese NLP**: SudachiPy morphological analysis for high-quality Japanese search.
- **Microservices Architecture**: Read-only Search API, Write-only Indexer, distributed Crawler workers.
- **Free API**: Anonymous access with IP-based rate limiting (100 req/min).

## Search API

Base URL: `https://palebluesearch.com/api/v1`

### Quick Example

```bash
curl "https://palebluesearch.com/api/v1/search?q=python+web+framework"
```

```json
{
  "query": "python web framework",
  "total": 42,
  "page": 1,
  "per_page": 10,
  "last_page": 5,
  "hits": [
    {
      "url": "https://example.com/fastapi",
      "title": "FastAPI - Modern Python Web Framework",
      "snip": "A modern, fast web framework for building APIs with <mark>Python</mark>...",
      "snip_plain": "A modern, fast web framework for building APIs with Python...",
      "rank": 12.5,
      "indexed_at": "2026-03-01T12:00:00.000000+00:00",
      "published_at": "2026-02-28T09:30:00+00:00"
    }
  ],
  "mode": "auto",
  "request_id": "a1b2c3d4e5f6"
}
```

### Authentication

Anonymous access is available with IP-based rate limiting (100 req/min).
For higher limits, use an API key via header or query parameter:

```bash
# Header (recommended)
curl -H "X-API-Key: pbs_your_key_here" \
  "https://palebluesearch.com/api/v1/search?q=rust"

# Query parameter
curl "https://palebluesearch.com/api/v1/search?q=rust&api_key=pbs_your_key_here"
```

With a valid key, the response includes usage info:

```json
{
  "usage": { "daily_used": 5, "daily_limit": 1000 }
}
```

### Search Modes

| Mode | Description |
|---|---|
| `auto` | Automatically selects the best mode (default) |
| `bm25` | Classic keyword matching with BM25 scoring |
| `hybrid` | BM25 + vector semantic search with RRF fusion |
| `semantic` | Pure vector similarity search |

```bash
curl "https://palebluesearch.com/api/v1/search?q=machine+learning&mode=hybrid"
```

### Pagination

```bash
curl "https://palebluesearch.com/api/v1/search?q=python&limit=20&page=2"
```

### Click Tracking

Report user clicks to improve search quality:

```bash
curl -X POST "https://palebluesearch.com/api/v1/search/click" \
  -H "Content-Type: application/json" \
  -d '{"request_id": "a1b2c3d4e5f6", "query": "python", "url": "https://example.com", "rank": 1}'
```

### Error Codes

| Code | Description |
|---|---|
| `401` | Invalid API key |
| `429` | Rate limit exceeded |

## Documentation

*   **[Architecture](./docs/architecture.md)**: System design and modules.
*   **[Setup Guide](./docs/setup.md)**: Installation, Docker, and local development.
*   **[API Reference](./docs/api.md)**: Endpoints and usage details.
*   **[Japanese Tokenization](./docs/japanese_tokenization.md)**: Details on SudachiPy and custom indexing.

## Quick Start

### Prerequisites
- Docker & Docker Compose

### Running the App

```bash
# Build and start services (Frontend, Indexer, Crawler)
docker compose up --build -d
```

Once running, access the following:

- **Search UI**: [http://localhost:8083/](http://localhost:8083/)
- **API Docs**: [http://localhost:8083/docs](http://localhost:8083/docs)
- **Indexer API**: [http://localhost:8081/docs](http://localhost:8081/docs)
- **Crawler API**: [http://localhost:8082/docs](http://localhost:8082/docs)

## Architecture

- **Web Node (Frontend)**: FastAPI (serves UI and Search API).
- **Write Node (Indexer)**: FastAPI (handles Ingestion and Vectors).
- **Worker Node (Crawler)**: Custom Python worker using `aiohttp` and `BeautifulSoup`.
- **Database**: PostgreSQL for production, SQLite for local development.

## License

MIT
