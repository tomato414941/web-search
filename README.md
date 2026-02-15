# Web Search Engine

A custom full-text search engine built with **FastAPI** and **PostgreSQL** (production),
with **SQLite** for local development. It features a parallel crawler, a separate indexer
with SudachiPy tokenization, and a modern UI.

## Features

- **Full-Text Search**: Custom inverted index with **SudachiPy** (Japanese morphological analyzer).
- **Microservices Architecture**:
    - **Search Service (Frontend)**: Read-only, scalable, serving UI & API.
    - **Indexer Service**: Dedicated Write-node for heavy processing (Tokenization, Embedding).
    - **Crawler Service**: Distributed worker nodes.
- **CQRS-lite**: Read (`:8083`) and Write (`:8081`) paths are split by service with a shared DB.
- **Parallel Crawler**: SQLite-based URL frontier/history for crawl state.
- **Internationalization (i18n)**: UI supports both English and Japanese.
- **API First**: Provides JSON endpoints for search, stats, and crawling.

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
