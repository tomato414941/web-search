# Refactor: Move Tests to Indexer Service

## Goal
Now that the Indexer is a separate service, we must move its tests from `frontend` to `indexer` and remove dead code.

## Broken State Identified
1.  `frontend/tests/test_indexer_api.py` exists but the endpoint `/api/v1/indexer/page` was removed from Frontend. **These tests will fail.**
2.  `indexer/` service has no tests.
3.  `frontend/src/frontend/indexer/service.py` is now dead code (Frontend is Read-Only).

## Proposed Changes

### 1. Create Indexer Tests (`indexer/tests/`)
- Create `indexer/tests/conftest.py` (Setup FastAPI TestClient for Indexer app).
- Port `frontend/tests/test_indexer_api.py` -> `indexer/tests/test_api.py`.
    - Update imports to use `app.main` instead of `frontend.main`.
    - Ensure it uses the shared `search.db` pattern.

### 2. Clean Frontend
- **Delete** `frontend/tests/test_indexer_api.py`.
- **Delete** `frontend/src/frontend/indexer/service.py`.
- **Keep** `frontend/src/frontend/indexer/analyzer.py` (Used by Search Logic for tokenization).
    - *Note*: Ideally `analyzer` should move to `shared`, but leaving it is safer for now.

### 3. Verify
- Run `pytest frontend` -> Should pass (no 404s).
- Run `pytest indexer` -> Should pass (verifying new service).

## Instructions for Agent
- Use `pytest` to verify passing status.
- Ensure `indexer` package is installed in editable mode or PYTHONPATH is set correctly for tests.
