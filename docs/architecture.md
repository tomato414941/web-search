# Architecture Overview

The `web-search` project follows a **Modular Monolith** architecture designed for clear separation of concerns, testability, and scalability.

## High-Level Design

The system consists of three main subsystems:

1.  **Web API (FastAPI)**: Handles user requests, search queries, and serves the UI.
2.  **Crawler (Async Worker)**: Background process that discovers, fetches, and parses web pages.
3.  **Indexer & Search Core**: Business logic for processing content (tokenization, embedding) and retrieving it (FTS5, Vector Search).

```mermaid
graph TD
    Client[User / Browser] --> API[Web API (FastAPI)]
    API --> SearchSvc[Search Service]
    API --> StatsSvc[Stats Service]

    subgraph Core Logic
        SearchSvc --> DB[(SQLite FTS5)]
        SearchSvc --> Embed[Embedding Service]
        Indexer[Indexer Service] --> DB
        Indexer --> Embed
    end

    subgraph Crawler System
        Scheduler[Crawl Scheduler] --> Redis[(Redis Frontier)]
        Worker[Async Worker] --> Redis
        Worker --> Parser[HTML Parser]
        Parser --> Indexer
    end
```

## Directory Structure

The source code is located in `src/web_search` and organized by **Domain/Layer**:

| Directory | Purpose | Key Components |
| :--- | :--- | :--- |
| `api/` | **Presentation Layer**. Handles HTTP requests. | `main.py`, `routers/` |
| `services/` | **Business Logic Layer**. Orchestrates operations. | `search.py`, `ranking.py`, `embedding.py` |
| `crawler/` | **Crawling Subsystem**. Fetches content. | `scheduler.py`, `worker.py`, `parser.py` |
| `indexer/` | **Indexing Subsystem**. Processes raw data. | `service.py`, `analyzer.py` |
| `db/` | **Infrastructure Layer**. Data access details. | `sqlite.py`, `redis.py` |
| `core/` | **Cross-cutting Concerns**. Config & Utils. | `config.py`, `utils.py` |

## Key Design Patterns

### 1. Service-Repository Pattern
We separate "Business Logic" (Services) from "Data Access" (Repositories/DB modules).
*   **Services** (`services/`) know *what* to do (e.g., "Search for X").
*   **DB Modules** (`db/`) know *how* to do it (e.g., `SELECT * FROM pages WHERE...`).

### 2. Dual-Column Storage (Indexed vs. Unindexed)
To optimize FTS5 size and performance, we often store the same content twice with different purposes:
*   `content`: Tokenized and indexed for searching. (Stripped of heavy HTML tags).
*   `raw_content`: stored as `UNINDEXED` in FTS5 (or a separate table) for display, preserving formatting but not contributing to the index size.

### 3. Asynchronous Crawler
The crawler uses `aiohttp` for high-concurrency fetching. It communicates with the rest of the system primarily through **Redis** (for the URL queue) and the **Indexer Service** (for saving results).
