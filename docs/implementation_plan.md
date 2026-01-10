# Global Refactoring & Architectural Alignment Plan (Completed)

> [!IMPORTANT]
> **Status**: Implemented
> **Date**: Jan 2026
> **Result**: All changes below have been applied and verified. This document serves as a historical record.


## Goal
Transform the codebase to the "Ideal State" defined in the Architecture Guide (Jan 2026). This involves enforcing the "Lean Shared Kernel" pattern, removing deprecated logic, and modernizing the Admin Dashboard.

## 1. Shared Library Purification
The `shared` library must contain **zero** business logic or deprecated wrappers.

### Changes
*   **[DELETE] `shared/src/shared/core/config.py`**: Remove the deprecated wrapper.
*   **[DELETE] `shared/src/shared/core/constants.py`**: Remove the deprecated wrapper.
*   **[MODIFY] `shared/src/shared/db/redis.py`**: Remove the deprecated `calculate_score` function.
    *   *Note: This strictly enforces that scoring is a Crawler domain concern.*

## 2. Frontend Modernization
Establish proper boundaries for the Frontend service.

### Changes
*   **[NEW] `frontend/src/frontend/core/config.py`**:
    *   Create a clean `Settings` class inheriting from `InfrastructureSettings` (shared).
    *   This will be the single source of truth for Frontend configuration.
*   **[Refactor Imports]**:
    *   Update all `from shared.core.config import settings` to `from frontend.core.config import settings`.
    *   Update all `from shared.core.constants import MESSAGES` to `from frontend.i18n.messages import MESSAGES`.

## 3. Crawler Service API Expansion
Replace code sharing with API communication for scoring logic.

### Changes
*   **[NEW] `crawler/src/app/api/routes/scoring.py`**:
    *   Add `POST /score/predict` endpoint.
    *   Accepts `url`, `parent_score`, `visits`.
    *   Returns calculated score using `app.domain.scoring`.
*   **[MODIFY] `crawler/src/app/main.py`**: Register the new router.
*   **[MODIFY] `frontend/src/frontend/api/routers/search.py`**:
    *   Update `api_predict` to call the Crawler Service (`POST /score/predict`) instead of importing `calculate_score` locally.

## 4. Admin Dashboard Refactoring (Templating)
Separate Presentation (HTML) from Logic (Python) in the Admin Dashboard.

### Changes
*   **[NEW] `frontend/src/frontend/templates/admin/base.html`**: Base layout.
*   **[NEW] `frontend/src/frontend/templates/admin/dashboard.html`**: Main stats view.
*   **[NEW] `frontend/src/frontend/templates/admin/seeds.html`**: Seed URL management.
*   **[NEW] `frontend/src/frontend/templates/admin/history.html`**: Crawl history view.
*   **[NEW] `frontend/src/frontend/templates/admin/login.html`**: Login page.
*   **[MODIFY] `frontend/src/frontend/api/routers/admin.py`**:
    *   Replace inline strings with `templates.TemplateResponse`.

## Verification Plan

### Automated Tests
Run existing tests to ensure no regressions after import updates.
```bash
# Frontend Tests
cd frontend/src && pytest ../tests

# Crawler Tests
cd crawler/src && pytest ../tests

# Shared Tests
cd c:\projects\web-search && pytest shared/tests
```

### Manual Verification
1.  **Frontend Config**: Verify app starts with `python -m frontend.api.main`.
2.  **Scoring Proxy**:
    *   Run Crawler and Frontend.
    *   Call `GET http://localhost:8080/api/predict?url=https://example.com`.
    *   Confirm JSON response.
3.  **Admin Dashboard**:
    *   Login to `/admin/login`.
    *   View Dashboard, Seeds, History pages.
    *   Confirm styles and data loading.
