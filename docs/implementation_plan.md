# Feature: Admin Dashboard Expansion & CSP Fix

## Goal
1.  **Fix CSP**: Allow Google Favicons to be displayed.
2.  **Crawler Control**: Add GUI controls to the Admin Dashboard to Start/Stop the crawler.
3.  **Search Analytics**: Track user queries to identify content gaps.

## Problem
-   **CSP**: Blocks external images from `google.com`.
-   **Admin UI**: No way to control the crawler (Start/Stop) without using raw API calls.
-   **Analytics**: No visibility into what users are searching for and whether they are finding results.

## Proposed Changes

### 1. Fix CSP (Content Security Policy)

#### [MODIFY] [frontend/src/frontend/api/main.py](file:///c:/projects/web-search/frontend/src/frontend/api/main.py)
-   Update `SecurityHeadersMiddleware` to include `https://www.google.com` in `img-src`.

### 2. Admin Dashboard Expansion (Crawler Control)

#### [MODIFY] [frontend/src/frontend/api/routers/admin.py](file:///c:/projects/web-search/frontend/src/frontend/api/routers/admin.py)
-   Add `POST /admin/crawler/start` endpoint (Proxies to `CRAWLER_SERVICE_URL/api/v1/worker/start`).
-   Add `POST /admin/crawler/stop` endpoint (Proxies to `CRAWLER_SERVICE_URL/api/v1/worker/stop`).
-   Update `get_stats()` to include detailed worker status (running state).

#### [MODIFY] [frontend/src/frontend/templates/admin/dashboard.html](file:///c:/projects/web-search/frontend/src/frontend/templates/admin/dashboard.html)
-   Add a "Crawler Control" card.
-   Add Start/Stop buttons that submit forms to the new admin endpoints.
-   Display current worker status (Running/Stopped).

### 3. Search Analytics

#### [NEW] [frontend/src/frontend/models/analytics.py](file:///c:/projects/web-search/frontend/src/frontend/models/analytics.py)
-   Define `SearchLog` model (query, timestamp, result_count, user_agent).

#### [MODIFY] [frontend/src/frontend/core/db.py](file:///c:/projects/web-search/frontend/src/frontend/core/db.py)
-   Add `search_logs` table creation to `init_db`.

#### [MODIFY] [frontend/src/frontend/api/routers/search_api.py](file:///c:/projects/web-search/frontend/src/frontend/api/routers/search_api.py)
-   Log every search request to the `search_logs` table (using `BackgroundTasks` to match performance).

#### [NEW] [frontend/src/frontend/api/routers/analytics.py](file:///c:/projects/web-search/frontend/src/frontend/api/routers/analytics.py)
-   Create a new router for analytics data access.

#### [NEW] [frontend/src/frontend/templates/admin/analytics.html](file:///c:/projects/web-search/frontend/src/frontend/templates/admin/analytics.html)
-   Create an analytics view showing:
    -   Top Queries (Last 7 days).
    -   Zero-Hit Queries (Content Gaps).

#### [MODIFY] [frontend/src/frontend/api/routers/admin.py](file:///c:/projects/web-search/frontend/src/frontend/api/routers/admin.py)
-   Add `/admin/analytics` route and link it in the navigation.

## Verification Plan

### Manual Verification
1.  **CSP**: Verify favicons appear in search results.
2.  **Crawler Control**:
    -   Click "Start" in Admin Dashboard -> Verify status changes to "Running".
    -   Click "Stop" -> Verify status changes to "Stopped" (Graceful).
3.  **Analytics**:
    -   Perform searches ("test", "unknown_keyword").
    -   Go to `/admin/analytics`.
    -   Verify "test" appears in "Top Queries".
    -   Verify "unknown_keyword" appears in "Zero-Hit Queries".
