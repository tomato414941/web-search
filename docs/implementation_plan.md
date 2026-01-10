# Refactor: Move Tests & Shared Logic

## Goal
Complete the Indexer separation by migrating tests and moving shared domain logic (Analyzer) to the `shared` library.

## Current Issues
1.  **Broken Tests**: `frontend/tests/test_indexer_api.py` fail because the endpoint moved to Indexer.
2.  **Code Duplication**: `analyzer.py` exists in both `frontend` and `indexer`.
3.  **Dead Code**: `frontend/src/frontend/indexer/service.py` is unused.

## Detailed Steps

### 1. Consolidate Analyzer (Shared Logic)
- **Move**: `frontend/src/frontend/indexer/analyzer.py` -> `shared/src/shared/analyzer.py`.
- **Delete Duplicates**:
    - Delete `frontend/src/frontend/indexer/analyzer.py`
    - Delete `indexer/src/app/services/analyzer.py`
- **Refactor Imports**:
    - Update `frontend/src/frontend/services/search.py` to import from `shared.analyzer`.
    - Update `indexer` service files to import from `shared.analyzer`.

### 2. Migrate Tests
- **Create**: `indexer/tests/conftest.py` (Setup FastAPI TestClient for Indexer).
- **Move**: `frontend/tests/test_indexer_api.py` -> `indexer/tests/test_api.py`.
    - Refactor imports to use `app.main` (Indexer App).
    - Ensure tests use `shared.analyzer` if needed.
- **Delete**: `frontend/tests/test_indexer_api.py`.

### 3. Cleanup Frontend
- **Delete Directory**: `frontend/src/frontend/indexer/` (Should be empty or contain only dead code now).

### 4. Verify
- Run `pytest shared` -> Check analyzer tests (if any).
- Run `pytest frontend` -> Should pass (no 404s, search works using shared analyzer).
- Run `pytest indexer` -> Should pass (API works).

## Instructions for Agent
- Be careful with circular imports when moving to shared.
- Analyzer usually depends on `SudachiPy`, ensuring `shared` dependencies are installed.
