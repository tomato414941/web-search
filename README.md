# Web Search Engine

A custom full-text search engine built with **FastAPI**, **Redis**, and **SQLite FTS5**.
It features a parallel crawler, a modern UI with theme support, and internationalization (i18n).

## Features

- **Full-Text Search**: Powered by SQLite FTS5 with **Trigram Tokenizer** for multilingual support (English & Japanese).
- **Parallel Crawler**: Uses **Redis** as a URL frontier to manage crawl queues efficiently.
- **Polite Crawling**: Respects `robots.txt` rules using `urllib.robotparser`.
- **Modern UI**: Clean interface with "Modern" (Glassmorphism) and "Simple" layout modes.
- **Internationalization (i18n)**: UI supports both English and Japanese.
- **API First**: Provides JSON endpoints for search, stats, and crawling.

## Documentation

For detailed information, please refer to the following documents:

*   **[Architecture](./docs/architecture.md)**: System design, modules, and key patterns.
*   **[Setup Guide](./docs/setup.md)**: Installation, Docker, and local development.
*   **[API Reference](./docs/api.md)**: Endpoints and usage details.
*   **[Japanese Tokenization](./docs/japanese_tokenization.md)**: Details on SudachiPy and FTS5 integration.


## Architecture

- **Web App**: FastAPI (serves UI and API).
- **Crawler**: Custom Python worker using `requests` and `BeautifulSoup`.
- **Database**: SQLite (FTS5) for index, Redis for crawl queue.

## Quick Start

### Prerequisites
- Docker & Docker Compose

### Running the App

```bash
# Build and start services in the background
docker compose up --build -d
```

Once running, access the following:

- **Search UI**: [http://localhost:8080/](http://localhost:8080/)
- **API Docs**: [http://localhost:8080/docs](http://localhost:8080/docs)
- **Stats API**: [http://localhost:8080/api/stats](http://localhost:8080/api/stats)

## API Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/search` | `GET` | Perform a search. Params: `q`, `limit`, `page`. |
| `/api/stats` | `GET` | Get system stats (index size, queue count). |
| `/api/crawl` | `POST` | Submit a URL to be crawled. JSON: `{"url": "..."}` |
| `/health` | `GET` | Health check. |

## Development & Testing

### Run the Server
```bash
# Using uvicorn directly
uvicorn web_search.api.main:app --reload --port 5000

# OR simply (using entry block in main)
python -m web_search.api.main
```

### Run the Crawler (Async)
```bash
python -m web_search.crawler.scheduler
```
*Note: Ensure Redis is running locally.*

### Run Tests
```bash
pytest
```

## Configuration

Environment variables can be set in `.env`:

```env
RESULTS_LIMIT=10
CRAWL_WORKERS=3
CRAWL_USER_AGENT="SearchBot/1.0 ..."
# see .env.example or docker-compose.yml for more
```

## License

MIT
