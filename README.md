# PaleBlueSearch

**Web Search API for AI Agents** — Quality-focused search built for LLMs and autonomous agents.

A full-stack search engine with its own crawler, BM25 ranking,
content quality scoring, and Japanese NLP support. Designed to return clean,
high-quality content that AI agents can trust.

## Features

- **AI-Agent-Optimized Ranking**: Every hit includes transparency metadata (`temporal_anchor`, `authorship_clarity`, `factual_density`, `origin_score`) so AI agents can make informed decisions.
- **Information Origin**: Documents classified as spring/river/delta/swamp based on link direction — primary sources rank higher than aggregation.
- **Factual Density**: Scores verifiable facts per unit of text (numbers, dates, citations, code, named entities) — replaces shallow word-count quality.
- **Clean Content Extraction**: [trafilatura](https://trafilatura.readthedocs.io/) strips navigation, footers, and sidebars — only main content is indexed.
- **Million-scale Indexing**: Own crawler with robots.txt compliance and authorship metadata extraction.
- **Japanese NLP**: SudachiPy morphological analysis for high-quality Japanese search.
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
      "published_at": "2026-02-28T09:30:00+00:00",
      "temporal_anchor": 1.0,
      "factual_density": 0.72,
      "origin_score": 0.85,
      "origin_type": "spring"
    }
  ],
  "mode": "bm25",
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
| `auto` | Alias of `bm25` (default) |
| `bm25` | Classic keyword matching with BM25 scoring |

```bash
curl "https://palebluesearch.com/api/v1/search?q=machine+learning&mode=bm25"
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

*   **[Product Direction](./docs/product-direction.md)**: Core problem statement, mission, principles, and anti-goals.
*   **[Search Evaluation](./docs/search-evaluation.md)**: Golden queries and manual relevance checks.
*   **[Search Ranking Policy](./docs/search-ranking-policy.md)**: Proposed minimal ranking policy for navigational and reference queries.
*   **[Architecture](./docs/architecture.md)**: System design and modules.
*   **[Content Quality](./docs/content-quality.md)**: Quality scoring strategy and ranking integration.
*   **[Setup Guide](./docs/setup.md)**: Installation, Docker, local development, and CI entrypoints.
*   **[API Reference](./docs/api.md)**: Endpoints and usage details.
*   **[Japanese Tokenization](./docs/japanese_tokenization.md)**: Details on SudachiPy and custom indexing.
*   **[Coolify Staging](./docs/coolify-staging.md)**: Staging topology and deployment model.
*   **[HTML Storage Design Note](./docs/html-storage.md)**: Archived design idea, not part of the current runtime.

## Quick Start

### Prerequisites
- Docker & Docker Compose

### Running the App

```bash
# Build and start the default lightweight stack
docker compose up --build -d
```

Once running, access the following:

- **Search UI**: [http://localhost:8083/](http://localhost:8083/)
- **API Docs**: [http://localhost:8083/docs](http://localhost:8083/docs)
- **Indexer API**: [http://localhost:8081/docs](http://localhost:8081/docs)

To start the optional crawler and search stack as well:

```bash
COMPOSE_PROFILES=search,crawler docker compose up --build -d
```

- `search`: starts `opensearch`
- `search-backfill`: runs `opensearch-backfill` as a one-off backfill job
- `crawler`: starts `crawler`
- `embedding`: starts `embedding-backfill`
- `monitoring`: starts `prometheus` and `grafana`
- **Crawler API**: [http://localhost:8082/docs](http://localhost:8082/docs) when the `crawler` profile is enabled

To run the OpenSearch backfill manually:

```bash
COMPOSE_PROFILES=search,search-backfill docker compose up --build opensearch-backfill
```

To enable the monitoring stack locally:

```bash
COMPOSE_PROFILES=monitoring docker compose up --build -d
```

- **Prometheus**: [http://localhost:9090/targets](http://localhost:9090/targets)
- **Grafana**: [http://localhost:3000/](http://localhost:3000/) (`admin` / `admin-change-me` by default)

## Architecture

- **Web Node (Frontend)**: FastAPI (serves UI and Search API, scope match re-ranking, claim diversity).
- **Write Node (Indexer)**: FastAPI (handles ingestion, signal scoring, vectors).
- **Worker Node (Crawler)**: Custom Python worker using `aiohttp` and `trafilatura` with metadata extraction.
- **Database**: PostgreSQL for production, SQLite for local development.

## License

MIT
