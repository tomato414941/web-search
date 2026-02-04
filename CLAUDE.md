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
export ENVIRONMENT=development
export PYTHONPATH=frontend/src
uvicorn frontend.api.main:app --reload --port 8000

# Run tests
export ENVIRONMENT=test
cd frontend && pytest tests/ -v
cd shared && pytest tests/ -v

# Lint
ruff check frontend/src/ shared/src/ crawler/src/
ruff format frontend/src/ shared/src/ crawler/src/
```

## Pre-commit Verification

- Run `pre-commit run --all-files` before committing to catch issues early
- When testing a new service, install its dependencies first (e.g., `pip install -r crawler/requirements.txt`)

## Architecture

Microservices architecture with CQRS-lite pattern:

- **frontend** (`:8080`): Read-only search service with UI, uses FastAPI + Jinja2
- **indexer** (`:8081`): Write-node for tokenization and embedding
- **crawler** (`:8082`): Distributed crawler with API for queue/worker management, uses Redis as URL frontier
- **shared**: Common library (DB, search logic, config) installed as editable package

### Database

- **Production**: PostgreSQL 16 (Docker)
  - Environment variable: `DATABASE_URL=postgresql://websearch:<password>@postgres:5432/websearch`
- **Local Development**: SQLite (auto-selected when `DATABASE_URL` is not set)
- **Search Index**: Custom inverted index (NOT FTS5)
  - Reason: Integration with SudachiPy (Japanese morphological analyzer)
- Connection logic: `shared/src/shared/db/search.py`

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

- **Service name**: paleblue search
- **Domain**: https://palebluesearch.com/
- **Server**: Hetzner SG (5.223.74.201)
  - Spec: CPX22 (2 vCPU / 4GB RAM / 80GB SSD)
  - Location: Singapore
  - SSH: `ssh dev@5.223.74.201`
- **Deploy**: `cd /home/dev/web-search && git pull && docker compose up -d --build`
- **Environment variables**: `/home/dev/web-search/.env`

## API Endpoints

- Search API: `/api/v1/search?q=<query>`
- Health: `/health`, `/healthz`, `/readyz` (root level)
- API docs: `/docs` (Swagger UI)
