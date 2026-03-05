# Setup Guide

## Prerequisites
- Docker & Docker Compose (recommended)
- Python 3.11+
- Git

## Docker Setup (Recommended)
Run the default lightweight stack with Docker Compose:

```bash
docker compose up --build -d
```

Services and ports:
- Frontend (UI + Search API): http://localhost:8083
- Indexer (Write API): http://localhost:8081
- PostgreSQL: internal to the compose network

Enable optional services only when needed:

```bash
COMPOSE_PROFILES=search,crawler docker compose up --build -d
```

- `search`: starts `opensearch` and `opensearch-backfill`
- `crawler`: starts `crawler`
- `embedding`: starts `embedding-backfill`

## Local Development Setup
This repo is a folder-separated monorepo. Install the shared package first, then service deps.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e shared/
pip install -r frontend/requirements.txt
pip install -r indexer/requirements.txt
pip install -r crawler/requirements.txt
```

### Environment Configuration
Copy and load the root `.env` file:

```bash
cp .env.example .env
set -a
source .env
set +a
```

Required variables for local runs:
- `ENVIRONMENT=development`
- `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_SESSION_SECRET`
- `INDEXER_API_KEY`
- `CRAWLER_SERVICE_URL` and `INDEXER_API_URL` when running multiple services locally

Optional:
- `OPENAI_API_KEY` for semantic search
- `DATABASE_URL` if you want to use PostgreSQL locally (otherwise SQLite is used)

### Running Services
Use separate terminals:

```bash
export PYTHONPATH=frontend/src
uvicorn frontend.api.main:app --reload --port 8083
```

```bash
export PYTHONPATH=indexer/src
uvicorn app.main:app --reload --port 8081
```

```bash
export PYTHONPATH=crawler/src
uvicorn app.main:app --reload --port 8082
```

## Linting and Formatting

```bash
ruff check frontend/src/ shared/src/ crawler/src/ indexer/src/
ruff format frontend/src/ shared/src/ crawler/src/ indexer/src/
```

## Pre-commit Hooks

Install pre-commit hooks to catch lint and test failures before pushing:

```bash
pip install pre-commit
pre-commit install
```

This runs `ruff` (lint + format) and service-specific `pytest` on every commit.

## Running Tests
Tests are split by service.

```bash
pytest shared/tests
pytest frontend/tests
pytest indexer/tests
pytest crawler/tests
```

## Staging on Coolify
For production-like staging setup on Coolify, see:

- `docs/coolify-staging.md`
- `scripts/ops/coolify_staging_smoke.sh`
