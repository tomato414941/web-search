# Architecture Overview

The `web-search` project follows a **Service-Based Architecture** designed for clear separation of concerns, scalability, and independent deployment of Read/Write workloads (CQRS-lite).

## High-Level Design

The system consists of three independent services managed in a Monorepo:

1.  **Frontend Service (Search Cluster)**: 
    -   **Role**: UI, Search API (Read-Only), Admin Dashboard.
    -   **Stack**: FastAPI + SQLite (WAL Mode).
    -   **Port**: `8080`.
    -   **Scaling**: Can scale horizontally (Shared DB file).
    -   **Dependencies**: Depends on `shared` for DB models/Analyzer.
2.  **Indexer Service (Write Cluster)**: 
    -   **Role**: Ingestion, Tokenization (Japanese), Embedding (OpenAI).
    -   **Stack**: FastAPI + SQLite (WAL Mode) + SudachiPy.
    -   **Port**: `8081`.
    -   **Scaling**: Single Writer (SQLite constraint), but decoupled from Read load.
3.  **Crawler Service (Worker Node)**: 
    -   **Role**: Fetching, Parsing, Queue Management.
    -   **Stack**: FastAPI + Redis (Frontier).
    -   **Port**: `8000`.
    -   **Communication**: Sends data to Indexer via HTTP.

```mermaid
graph TD
    Client[User / Browser] --> Frontend[Frontend Service (8080)]
    
    subgraph Data Layer
        SQLite[(Shared SQLite WAL)]
    end

    subgraph Crawler Node
        Crawler[Crawler Service (8000)] --> Redis[(Redis Frontier)]
        Crawler -- POST /page --> Indexer
    end
    
    subgraph Write Cluster
        Indexer[Indexer Service (8081)]
    end

    Frontend -- Read Search --> SQLite
    Indexer -- Write Index --> SQLite
    Frontend -- HTTP Status/Control --> Crawler
```

## Directory Structure

The project uses a **Folder-Separated Monorepo** pattern:

| Directory | Package Name | Purpose | Key Components |
| :--- | :--- | :--- | :--- |
| `frontend/` | `frontend` | **Search Cluster**. UI & Search Logic. | `api/routers/search_api.py`, `services/search.py` |
| `indexer/` | `app` | **Write Cluster**. Indexing & Embedding. | `api/routes/indexer.py`, `services/indexer.py` |
| `crawler/` | `app` | **Worker Node**. Fetching & Parsing. | `workers/tasks.py`, `api/routes/crawl.py` |
| `shared/` | `shared` | **Shared Kernel**. Domain Logic & Infra. | `db/search.py`, `analyzer.py` (Sudachi) |
| `deployment/` | - | **IaC**. Docker & Configs. | `docker-compose.yml`, `.env.example` |

## Key Design Patterns

### 1. CQRS-lite (Separated Read/Write)
We separate the "Write" path (Indexer) from the "Read" path (Frontend).
*   **Indexer**: Heavy processing (Tokenization, Embedding Generation). Locking writes to SQLite.
*   **Frontend**: Fast reads. Uses SQLite WAL mode to read *while* Indexer is writing.

### 2. Shared Kernel (`shared`)
Common domain logic and infrastructure code live in `shared`.
*   **Database**: `shared.db.search` defines the schema and connection logic.
*   **Analyzer**: `shared.analyzer` defines how Japanese text is tokenized (SudachiPy), ensuring both Indexer (Write) and Frontend (Query) use the exact same logic.

### 3. Asynchronous Crawler
The crawler uses `aiohttp` for high-concurrency fetching. It is entirely decoupled from the storage layer.
*   It submits crawled data to **Indexer Service** via HTTP (`POST /api/v1/indexer/page`).
*   It does **not** write to SQLite directly.

## Tokenization Strategy
*   **Engine**: SQLite FTS5 with `tokenize='unicode61'` (Whitespace based).
*   **Pre-processing**: Python-side `JapaneseAnalyzer` (SudachiPy) converts Japanese text into space-separated tokens *before* sending to SQLite.
*   This hybrid approach allows us to use robust NLP libraries (Sudachi) while leveraging standard FTS5 features.
