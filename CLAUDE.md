# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
# Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e shared/
pip install -r frontend/requirements.txt

# Run frontend locally
export PYTHONPATH=frontend/src
uvicorn frontend.api.main:app --reload --port 8000

# Run tests
cd frontend && pytest tests/ -v
cd shared && pytest tests/ -v

# Run single test
pytest frontend/tests/test_search.py::test_function_name -v

# Lint
ruff check frontend/src/ shared/src/ crawler/src/
ruff format frontend/src/ shared/src/ crawler/src/

# Full local setup (all services)
pip install -r frontend/requirements.txt
pip install -r crawler/requirements.txt
pip install -r indexer/requirements.txt
```

## Pre-commit Verification

- Run `pre-commit run --all-files` before committing to catch issues early
- When testing a new service, install its dependencies first (e.g., `pip install -r crawler/requirements.txt`)

## Architecture

Microservices architecture with CQRS-lite pattern:

- **frontend** (`:8080`): Read-only search service with UI, uses FastAPI + Jinja2
- **indexer** (`:8081`): Write-node for tokenization and embedding
- **crawler** (`:8000`): Distributed crawler with API for queue/worker management, uses Redis as URL frontier
- **shared**: Common library (DB, search logic, config) installed as editable package

### Database
- **Production**: Turso (libsql) - set `TURSO_URL` and `TURSO_TOKEN` environment variables
- **Local**: SQLite - auto-selected when Turso env vars are not set
- **Search Index**: Custom inverted index (NOT FTS5)
  - Reason: Integration with SudachiPy (Japanese morphological analyzer)
- Connection logic in `shared/src/shared/db/search.py`

### Search Algorithm
- **BM25**: Keyword search (k1=1.2, b=0.75, title_boost=3.0)
- **Vector Search**: Semantic search with OpenAI embeddings
- **Hybrid Search**: Reciprocal Rank Fusion (RRF)
- **PageRank**: Link analysis scoring
- Tokenizer: SudachiPy Mode A

### Key Paths
- Frontend API: `frontend/src/frontend/api/main.py`
- Search logic: `shared/src/shared/search/searcher.py`
- BM25/Scoring: `shared/src/shared/search/scoring.py`
- Tokenizer: `shared/src/shared/analyzer.py`
- DB operations: `shared/src/shared/db/search.py`
- Indexer API: `indexer/src/app/main.py`
- Crawler workers: `crawler/src/app/workers/`

## Deployment

- **CI/CD**: GitHub Actions (`.github/workflows/ci.yml`)
- Push to `main` → test/lint → build Docker images → push to ghcr.io
- **Coolify**: Auto-deploys from ghcr.io container registry
- **Environment variables**: Set in Coolify dashboard (not in repo)

Docker images:
- `ghcr.io/tomato414941/web-search:latest` (frontend)
- `ghcr.io/tomato414941/web-search-indexer:latest`
- `ghcr.io/tomato414941/web-search-crawler:latest`

## API Endpoints

- Search API: `/api/v1/search?q=<query>`
- Health: `/api/v1/health`, `/healthz`, `/readyz`
- API docs: `/docs` (Swagger UI)
