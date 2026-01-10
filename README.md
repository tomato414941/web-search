# Web Search Engine

A custom full-text search engine built with **FastAPI**, **Redis**, and **SQLite FTS5**.
It features a parallel crawler, a separate high-performance indexer, and a modern UI with theme support.

## Features

- **Full-Text Search**: Powered by SQLite FTS5 with **Trigram Tokenizer** for multilingual support.
- **Microservices Architecture**:
    - **Search Service (Frontend)**: Read-only, scalable, serving UI & API.
    - **Indexer Service**: Dedicated Write-node for heavy processing (Tokenization, Embedding).
    - **Crawler Service**: Distributed worker nodes.
- **CQRS-lite**: Reads (`:8080`) are isolated from Writes (`:8081`) via SQLite WAL mode.
- **Parallel Crawler**: Uses **Redis** as a URL frontier.
- **Internationalization (i18n)**: UI supports both English and Japanese.
- **API First**: Provides JSON endpoints for search, stats, and crawling.

## Documentation

*   **[Architecture](./docs/architecture.md)**: System design and modules.
*   **[Setup Guide](./docs/setup.md)**: Installation, Docker, and local development.
*   **[API Reference](./docs/api.md)**: Endpoints and usage details.
*   **[Japanese Tokenization](./docs/japanese_tokenization.md)**: Details on SudachiPy and FTS5 integration.

## Quick Start

### Prerequisites
- Docker & Docker Compose

### Running the App

```bash
# Build and start services (Frontend, Indexer, Redis)
docker compose -f deployment/frontend/docker-compose.yml up --build -d
```

Once running, access the following:

- **Search UI**: [http://localhost:8080/](http://localhost:8080/)
- **API Docs**: [http://localhost:8080/docs](http://localhost:8080/docs)
- **Indexer API**: [http://localhost:8081/docs](http://localhost:8081/docs)

## Architecture

- **Web Node (Frontend)**: FastAPI (serves UI and Search API).
- **Write Node (Indexer)**: FastAPI (handles Ingestion and Vectors).
- **Worker Node (Crawler)**: Custom Python worker using `aiohttp` and `BeautifulSoup`.
- **Database**: Shared SQLite (FTS5) on persistent volume.

## License

MIT
