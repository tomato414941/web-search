# Global API Versioning (v1) Implementation

## Goal
Standardize all API endpoints in both Frontend and Crawler services to use the `/api/v1` prefix. This improves API design consistency and allows for future versioning.

## User Review Required
> [!IMPORTANT]
> **Breaking Change**: All external API calls and environment variables referencing API URLs must be updated to include `/v1`.
> - `INDEXER_API_URL` -> `.../api/v1/indexer/page`
> - `CRAWLER_SERVICE_URL` -> Base URL only, code appends `/api/v1/...` or update base? *Decision: Base URL remains host root, code appends `/api/v1`.*

## Proposed Changes

### 1. Crawler Service (`crawler/src/app/main.py`)
- Prefix all routers with `/api/v1`.
    - `crawl` -> `/api/v1` (merges to `/api/v1/urls`)
    - `worker` -> `/api/v1/worker`
    - `queue` -> `/api/v1` (merges to `/api/v1/status` etc)
    - `history` -> `/api/v1/history`
    - `health` -> `/api/v1/health` (or leave health at root? Usually root or `/health` is standard for probes, but `/api/v1/health` is fine too. Let's keep health global or check user pref. Standard practice: `/health` often global, but app routes under `/api`. Let's put everything under `/api/v1` for consistency as requested "ALL endpoints").

### 2. Frontend Service (`frontend/src/frontend/api/main.py`)
- Prefix all routers with `/api/v1`.
    - `search` -> `/api/v1/search`
    - `crawler` (proxy) -> `/api/v1/crawler/urls`
    - `stats` -> `/api/v1/stats`
    - `indexer` -> `/api/v1/indexer`
    - `admin` -> `/admin` (Keep standard UI routes at root/admin, only API routes get `/api/v1`? likely yes. User said "ALL endpoints", but usually means API endpoints. I will assume UI routes stay as is, API routes move).

### 3. Internal Clients (Update references)
- **Frontend** calling **Crawler**:
    - `frontend/api/routers/admin.py`: Update calls to `/api/v1/...`
    - `frontend/api/routers/stats.py`: Update calls to `/api/v1/status`
    - `frontend/api/routers/crawler.py`: Update calls to `/api/v1/urls`
- **Crawler** calling **Frontend (Indexer)**:
    - `crawler/services/indexer.py`: No hardcoded path, uses `INDEXER_API_URL`.
    - **Action**: Update `docker-compose.yml` `INDEXER_API_URL`.

### 4. Configuration Updates
- `deployment/crawler/docker-compose.yml`: Update `INDEXER_API_URL` to `http://${FRONTEND_IP}:8080/api/v1/indexer/page`
- `deployment/frontend/docker-compose.yml`: (If it has env vars for crawler, update them).

## Verification Plan
1. **Local Test**: Run services, curl endpoints with `/api/v1` prefix.
2. **Integration Test**: Check Admin Dashboard "Seeds" page (calls Frontend API -> Crawler API) and "Stats" page.
