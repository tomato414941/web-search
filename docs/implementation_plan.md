# Refactor: Separate Indexer Service (CQRS)

## Goal
Decouple the "Write" (Indexing) responsibility from the "Read" (Search) responsibility to prevent crawling/indexing from degrading search performance. This implements the **CQRS (Command Query Responsibility Segregation)** pattern.

## User Review Required
> [!IMPORTANT]
> **Architecture Change**: We will introduce a 3rd service: `Indexer Service`.
> - **Frontend**: Read-Only (Search UI & API).
> - **Indexer**: Write-Only (Receives pages from Crawler, calls OpenAI, writes to DB).
> - **Crawler**: Unchanged (just points to new Indexer URL).

## Proposed Changes

### 1. Create New Service: `indexer`
- Create `indexer/` directory (cloned structure from `frontend` or `crawler`).
- Move `frontend/src/frontend/indexer/` → `indexer/src/app/`
- Move `frontend/src/frontend/services/embedding.py` → `indexer/src/app/services/`
- Move `frontend/src/frontend/core/db.py` → `indexer/src/app/core/db.py` (Wait, Frontend still needs DB read access. Move to `shared`? No, we just moved it OUT of shared. Solution: *Now* we validly need a shared `db` module, or improved `shared` library usage, OR... **duplication for decoupling**? Or move `db.py` back to `shared` but explicitly as `shared.db.search_index`?
- *Better Approach*: Keep `frontend` as is for now, but create `indexer` service that *shares* the database file.
- **Decision**: To avoid massive refactoring of `db.py` again rapidly:
    - Frontend keeps `core/db.py` (Read capability).
    - Indexer gets a copy or imports if we move back config.
    - Let's move `db.py` to `shared/src/shared/db/search.py` (Valid shared kernel now).

### 2. Update Configuration
- **Docker**: Add `indexer` service in `docker-compose.yml`.
    - Ports: `8081` (Internal only?) or expose.
    - Volumes: Mount `/data` (Shared Volume) so both Frontend and Indexer see `search.db`.
- **Crawler Config**: Update `INDEXER_API_URL` -> `http://indexer:8081/api/v1/indexer/page`.

### 3. Refactor Embedding (Async Fix)
- Even in a separate service, blocking I/O is bad.
- Update `EmbeddingService` to use `AsyncOpenAI` client.

## Verification Plan
1. Start all 3 services.
2. Crawl a page -> Logs in Indexer.
3. Search -> Frontend returns result (reading from shared SQLite).
