# Documentation Update (Monorepo Alignment)

The current documentation in `docs/` refers to the legacy `src/web_search` structure. This plan outlines the updates required to make the documentation accurate for the current Folder-Separated Monorepo architecture.

## 1. Objectives

- Update `docs/setup.md` to use correct Monorepo paths and commands.
- Update `docs/architecture.md` to reflect the split between `frontend`, `crawler`, and `shared`.
- Update `docs/japanese_tokenization.md` to point to the correct file locations.
- Update `README.md` (root) to remove legacy references if necessary (optional, but good for consistency).

## 2. Changes Required

### `docs/setup.md`
- **Frontend Entry**: Change `web_search.api.main:app` to `frontend.api.main:app`.
- **Crawler Entry**: Change `web_search.crawler.scheduler` to `app.main:app` (or `python -m crawler.src.app.main`).
- **Dependencies**: Mention `frontend/requirements.txt`, `crawler/requirements.txt`, and `pip install -e shared`.
- **Docker**: Update instructions to reflect new services (if strictly necessary, though `docker compose up` might still work if `docker-compose.yml` was updated).

### `docs/architecture.md`
- **Directory Structure**:
  - Legacy: `src/web_search`
  - New:
    - `frontend/`: Web API & UI
    - `crawler/`: Independent Crawler Service
    - `shared/`: Common Logic (DB, Config)
- **High-Level Design**: Update to mention the distributed nature (Crawler is now a microservice).

### `docs/japanese_tokenization.md`
- **Code Location**: Change `src/web_search/indexer/analyzer.py` to `frontend/src/frontend/indexer/analyzer.py` (and/or `shared`).

### `docs/api.md`
- Verify default port (still 8080?) and endpoints. crawler control endpoints might be different if it's now a separate API.

## 3. Implementation Steps

1.  **Modify `docs/setup.md`**: Update installation and run commands.
2.  **Modify `docs/architecture.md`**: Rewrite directory structure section.
3.  **Modify `docs/japanese_tokenization.md`**: Update path references.
4.  **Review `docs/api.md`**: Ensure Crawler API section matches actual `crawler/src/app/api/routes` implementation (e.g. `POST /api/crawl` vs `POST /crawl`).

## 4. Verification Plan

### Manual Verification
- **Readability Check**: Verify the markdown renders correctly.
- **Accuracy Check**: Run the commands listed in `setup.md` to ensure they actually work.
  - `python -m frontend.api.main`
  - `python -m app.main` (from crawler dir)
