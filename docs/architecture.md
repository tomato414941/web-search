# Architecture Overview

The `web-search` project follows a **Modular Monolith** architecture designed for clear separation of concerns, testability, and scalability.

## High-Level Design

The system is a **Distributed System** managed in a Monorepo, consisting of improved isolation:

1.  **Frontend Service (Web Node)**: 
    - Pure FastAPI + SQLite (FTS5). 
    - **No Redis Dependency**: Authentication is stateless (HMAC).
    - Serves UI and JSON API.
2.  **Crawler Service (Worker Node)**: 
    - Independent FastAPI Microservice.
    - Manages its own sidecar **Redis** for the crawl frontier.
    - Sends data to Frontend via HTTP (Indexer API).
3.  **Shared Library (`shared`)**:
    - Common Core (Config, Logging, Utils).
    - Shared Database Schemas (SQLite models).

```mermaid
graph TD
    Client[User / Browser] --> Frontend[Frontend Service (8080)]
    Frontend --> SQLite[(SQLite FTS5)]
    
    subgraph Crawler Node
        Crawler[Crawler Service] --> Redis[(Redis Frontier)]
        Crawler -- HTTP POST --> Frontend
    end
```

## Directory Structure

The project uses a **Folder-Separated Monorepo** pattern:

| Directory | Package Name | Purpose | Key Components |
| :--- | :--- | :--- | :--- |
| `frontend/` | `frontend` | **Web Node**. UI & Search API. | `api/main.py`, `templates/`, `static/` |
| `crawler/` | `app` | **Worker Node**. Fetching & Parsing. | `api/routes/`, `workers/`, `main.py` |
| `shared/` | `shared` | **Kernel**. Shared logic. | `core/config.py`, `db/sqlite.py` |
| `deployment/` | - | **IaC**. Docker & Configs. | `docker-compose.yml`, `.env.example` |

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
