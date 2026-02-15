# Repository Guidelines

## Project Structure & Module Organization
This repo is a Python microservices stack. The main services live at the top level:
- `frontend/` FastAPI UI + read-only search API
- `indexer/` write-node for ingestion, tokenization, and embeddings
- `crawler/` distributed crawler workers and API
- `shared/` common library (DB, search logic, config), installed as an editable package
- `docs/` architecture and setup guides, plus API references
- `scripts/` operational scripts and utilities
Each service has its own `src/` and `tests/` directories (e.g., `frontend/src/`, `frontend/tests/`).

## Build, Test, and Development Commands
Run commands from the repo root unless noted:
- `python3 -m venv .venv && source .venv/bin/activate` to create and activate the venv.
- `pip install -e shared/` then `pip install -r frontend/requirements.txt` (repeat for `indexer/`, `crawler/`).
- `cp .env.example .env && set -a && source .env && set +a` to load env vars.
- `export PYTHONPATH=frontend/src && uvicorn frontend.api.main:app --reload --port 8083` to run the frontend API.
- `export PYTHONPATH=indexer/src && uvicorn app.main:app --reload --port 8081` to run the indexer.
- `export PYTHONPATH=crawler/src && uvicorn app.main:app --reload --port 8082` to run the crawler.
- `docker compose up --build -d` to start the full stack (frontend, indexer, crawler).
- `cd frontend && pytest tests/ -v` (repeat for `crawler/`, `indexer/`, `shared/`) to run tests.
- `ruff check frontend/src/ shared/src/ crawler/src/` and `ruff format ...` for linting/formatting.
- `pre-commit run --all-files` before committing to catch style issues.

## Coding Style & Naming Conventions
Python uses 4-space indentation and `ruff` formatting. Follow existing naming:
- Modules and functions: `snake_case`
- Classes: `PascalCase`
- Files and folders: match the local pattern in each service
Prefer small, focused modules and keep shared logic in `shared/`.

## Testing Guidelines
Tests use `pytest` and live under each service’s `tests/` directory. Name tests `test_*.py` with functions `test_*`. Add tests for new behavior and update fixtures when you change outputs or API contracts.

## Commit & Pull Request Guidelines
Commit messages follow a conventional prefix pattern: `feat: ...`, `fix: ...`, `refactor: ...`, `docs: ...`. Keep commits scoped and descriptive. For PRs, include:
- A concise summary and rationale
- Linked issues or tickets
- Test results (commands and outcomes)
- Screenshots for UI or template changes

## Security & Configuration Tips
Use `.env.example` as the template for local config. Never commit secrets from `.env`, tokens, or credentials. Local development defaults to SQLite when `DATABASE_URL` is not set; production requires explicit environment variables.
