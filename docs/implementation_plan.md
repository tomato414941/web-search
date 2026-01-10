# Fix: Tests and Documentation for API v1

## Goal
Restore system integrity by updating Test Suites and Documentation to reflect the new `/api/v1` URL structure. Currently, tests are failing because they query old endpoints.

## User Review Required
> [!IMPORTANT]
> Without this fix, CI/CD pipelines (if enabled) will fail, and future refactoring will be risky due to broken regression tests.

## Proposed Changes

### 1. Update Crawler Tests (`crawler/tests/`)
- **`test_api_endpoints.py`**:
    - `POST /urls` -> `POST /api/v1/urls`
    - `GET /queue` -> `GET /api/v1/queue`
    - `GET /status` -> `GET /api/v1/status`
    - `GET /history` -> `GET /api/v1/history`
    - `POST /worker/start` -> `POST /api/v1/worker/start`
    - `POST /worker/stop` -> `POST /api/v1/worker/stop`
    - `GET /worker/status` -> `GET /api/v1/worker/status`

### 2. Update Frontend Tests (`frontend/tests/`)
- **`test_indexer_api.py`**:
    - `POST /api/indexer/page` -> `POST /api/v1/indexer/page`
- **Other Tests**: Check `test_api_extensions.py` or others for hardcoded paths.

### 3. Update Documentation
- **`docs/architecture.md`**: Update any sequence diagrams or text referencing old API paths.
- **`deployment/README.md`**: Verify environment variable examples match the new defaults (which were just fixed, but double check docs match code).

## Verification Plan
1. **Run Crawler Tests**: `pytest crawler/tests/test_api_endpoints.py` (Must pass).
2. **Run Frontend Tests**: `pytest frontend/tests/test_indexer_api.py` (Must pass).
