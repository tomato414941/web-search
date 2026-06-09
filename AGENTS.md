# Repository Guidelines

## What This Project Is
PaleBlueSearch is a Web Search API for AI agents. The core value proposition is reliable search with useful transparency metadata such as freshness (`temporal_anchor`), factual richness (`factual_density`), and authorship clarity, so AI consumers can make informed decisions. The baseline retrieval path is BM25 plus a thin source-aware policy. Optional embedding enrichment exists for future experiments behind explicit opt-in, but it is not part of the baseline search contract today.

## Project Structure & Module Organization
This repo is a Python microservices stack (CQRS-lite: read and write paths are split by service). The repo is managed as a root `uv` workspace for local development, CI, and container dependency resolution.

The source-of-truth layout is:
- `apps/frontend/` FastAPI UI + read-only search API
- `apps/indexer/` write-node for ingestion, tokenization, signal computation, and OpenSearch sync
- `apps/crawler/` distributed crawler workers and health probes
- `packages/contracts/` typed service contracts and shared enums
- `packages/core/` runtime helpers, config, logging, retries, and test helpers
- `packages/postgres/` PostgreSQL access, migrations, and repositories
- `packages/web-model/` known URLs, observed links, and Web model repositories
- `packages/kernel/` search analyzer, query parsing, snippets, and scoring helpers
- `packages/opensearch/` OpenSearch client, mapping, and retrieval helpers
- `packages/indexing/` optional embedding backfill helpers plus PageRank and origin scoring support
- `packages/search-config/` canonical-source and search-eval policy data
- `packages/search-telemetry/` search request, impression, and click event storage
- `apps/mcp/` MCP server for AI agent integration (Claude Code, Claude Desktop)
- `docs/` architecture and setup guides, plus API references
- `scripts/` operational scripts (`ops/`), one-shot migrations (`migrations/`), dev tools (`dev/`)
Each service has its own `src/` and `tests/` directories (e.g., `apps/frontend/src/`, `apps/frontend/tests/`).
Use `apps/` and `packages/` paths directly for all new work.

## Build, Test, and Development Commands
Run commands from the repo root unless noted:
- `python3 -m venv .venv && source .venv/bin/activate` to create and activate the venv.
- `make sync` to install the full local workspace with `uv`.
- `make sync-frontend`, `make sync-indexer`, `make sync-crawler`, `make sync-packages`, or `make sync-mcp` for narrower installs.
- `cp .env.example .env && set -a && source .env && set +a` to load env vars.
- `uv run --package web-search-frontend uvicorn web_search_frontend.api.main:app --reload --port 8083` to run the frontend API.
- `uv run --package web-search-indexer uvicorn web_search_indexer.main:app --reload --port 8081` to run the indexer.
- `uv run --package web-search-crawler uvicorn web_search_crawler.main:app --reload --port 8082` to run the crawler.
- `docker compose up --build -d` to start the full stack (frontend, indexer, crawler).
- `make ci`, `make ci-frontend`, `make ci-packages`, `make ci-crawler`, `make ci-indexer`, and `make ci-mcp` to run tests.
- `ruff check apps/frontend/src/ packages/contracts/src/ packages/core/src/ packages/postgres/src/ packages/web-model/src/ packages/kernel/src/ packages/opensearch/src/ packages/indexing/src/ packages/search-config/src/ packages/search-telemetry/src/ apps/crawler/src/ apps/indexer/src/ apps/mcp/src/` and `ruff format ...` for linting/formatting.
- `pre-commit run --all-files` before committing to catch style issues.

## Branch Policy
- `main` is the source of truth for active development, compose definitions, and release promotion.
- Routine personal-development changes are committed and pushed directly to `main`.
- Use a feature branch only when a change is large, risky, or explicitly needs external review.
- STG has been decommissioned; do not add new staging deploy dependencies.
- Production deployment is an explicit operator action after CI passes.

## Coding Style & Naming Conventions
Python uses 4-space indentation and `ruff` formatting. Follow existing naming:
- Modules and functions: `snake_case`
- Classes: `PascalCase`
- Files and folders: match the local pattern in each service
Prefer small, focused modules.
Put contracts, runtime utilities, and policy/config data in the smaller `packages/` libraries first. Keep DB, retrieval, and indexing code in their dedicated packages instead of rebuilding a new monolith.

## Testing Guidelines
Tests use `pytest` and live under each service’s `tests/` directory. Name tests `test_*.py` with functions `test_*`. Add tests for new behavior and update fixtures when you change outputs or API contracts.

## Commit & Pull Request Guidelines
Commit messages follow a conventional prefix pattern: `feat: ...`, `fix: ...`, `refactor: ...`, `docs: ...`. Keep commits scoped and descriptive. For changes pushed directly to `main`, verify the relevant tests before pushing and watch CI after pushing.

## Security & Configuration Tips
Use `.env.example` as the template for local config. Never commit secrets from `.env`, tokens, or credentials. Local development and production both require explicit PostgreSQL configuration via `DATABASE_URL`.
