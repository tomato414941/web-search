# Architecture Overview

The `web-search` project follows a **Service-Based Architecture** designed for clear separation of concerns, scalability, and independent deployment of Read/Write workloads (CQRS-lite).

## High-Level Design

The system consists of three independent services managed in a Monorepo:

1.  **Frontend Service (Search Cluster)**:
    -   **Role**: UI, Search API (Read-Only), Admin Dashboard (Crawler Control, Analytics).
    -   **Stack**: FastAPI + PostgreSQL (production) or SQLite (local dev).
    -   **Port**: `8080`.
    -   **Scaling**: Can scale horizontally; shared DB in production.
    -   **Dependencies**: Depends on `shared` for DB models/Analyzer.
2.  **Indexer Service (Write Cluster)**:
    -   **Role**: Ingestion, Tokenization (Japanese), Embedding (OpenAI).
    -   **Stack**: FastAPI + PostgreSQL (production) or SQLite (local dev) + SudachiPy.
    -   **Port**: `8081`.
    -   **Scaling**: Write-heavy service; decoupled from read load.
3.  **Crawler Service (Worker Node)**:
    -   **Role**: Fetching, Parsing, Queue Management.
    -   **Stack**: FastAPI + PostgreSQL/SQLite (Frontier + History tables).
    -   **Port**: `8082`.
    -   **Communication**: Sends data to Indexer via HTTP.

```mermaid
graph TD
    Client[User / Browser] --> Frontend[Frontend Service (8080)]

    subgraph Data Layer
        DB[(PostgreSQL (prod) / SQLite (dev))]
    end

    subgraph Crawler Node
        Crawler[Crawler Service (8082)]
        Crawler -- POST /page --> Indexer
    end

    subgraph Write Cluster
        Indexer[Indexer Service (8081)]
    end

    Frontend -- Read Search --> DB
    Indexer -- Write Index --> DB
    Crawler -- Frontier/History --> DB
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
| `docs/` | - | **Documentation**. Architecture, setup, API docs. | `architecture.md`, `setup.md` |
| `.env.example` | - | **Environment Template**. Base config for local/dev. | `.env.example` |

## Key Design Patterns

### 1. CQRS-lite (Separated Read/Write)
We separate the "Write" path (Indexer) from the "Read" path (Frontend).
*   **Indexer**: Heavy processing (Tokenization, Embedding Generation).
*   **Frontend**: Fast reads. Both services share the same DB in production (PostgreSQL).

### 3. Shared Library (`shared/`)
*   **Database**: Supports PostgreSQL (production) and SQLite (local dev) with a custom schema (`documents`, `inverted_index`, `page_ranks`, `search_logs`).
*   **Search Engine (`shared.search`)**:
    *   **Custom Inverted Index**: Python-based indexing using `inverted_index` table.
    *   **Hybrid Search**: Combines BM25 (Keyword) and Vector (Semantic) scores using Reciprocal Rank Fusion (RRF).
    *   **Tokenizer**: `SudachiPy` for Japanese morphological analysis.
    *   **Scoring**: BM25 + PageRank boosting + Title boosting.

### 4. Data Flow
1.  **Crawl**: Crawler sends HTML to `Indexer Service` via API.
2.  **Index**: Indexer tokenizes text, generates embeddings (OpenAI), and updates the Inverted Index & Vector store.
3.  **Search**: Frontend uses `SearchEngine` to query the search index (PostgreSQL or SQLite).
