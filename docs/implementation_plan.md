# Fix: Configuration Drift & Unused Dependencies

## Goal
Fix critical configuration mismatches between Crawler and Frontend services that prevent local development stability, and remove unused dependencies.

## User Review Required
> [!NOTE]
> This creates a consistent "out-of-the-box" experience where services can talk to each other locally without complex `.env` setup.

## Proposed Changes

### 1. Fix Configuration Drift (`crawler/src/app/core/config.py`)
- **INDEXER_API_URL**: Update default from `http://frontend:5000/api/index` to `http://localhost:8080/api/v1/indexer/page`.
    - *Rationale*: Matches Frontend's actual default port (8080) and new API versioning.
- **INDEXER_API_KEY**: Update default from `dev-indexer-key...` to `dev-key`.
    - *Rationale*: Matches Frontend's default key.

### 2. Remove Unused Dependency (`frontend/requirements.txt`)
- Remove `redis` line.
    - *Rationale*: Frontend now uses HTTP API to talk to Crawler; direct Redis access was removed in previous refactoring.

## Verification
1. **Static Check**: Verify file content.
2. **Local Run**: `python -m app.main` in crawler should start without crashing on config validation (if any).
