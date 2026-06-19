# Setup Guide

## Status

Current local development reference.

## Related Docs

- [Documentation Guide](./README.md)
- [Architecture](./architecture.md)
- [Deployment Guide](./deployment.md)

## Scope

This guide covers local setup and day-to-day development only.
For production deployment and operational constraints, use [deployment.md](./deployment.md).

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

- `search`: starts `opensearch`
- `search-projection-rebuild`: rebuilds the OpenSearch search projection
- `crawler`: starts `crawler`
- `embedding`: runs the one-off `embedding-backfill` job; requires `OPENAI_API_KEY` and `EMBEDDING_ENRICHMENT_ENABLED=true`
- `monitoring`: starts `prometheus` and `grafana`

Rebuild the OpenSearch search projection only when you explicitly need it:

```bash
COMPOSE_PROFILES=search,search-projection-rebuild docker compose up --build search-projection-rebuild
```

Run this after changing OpenSearch projection values only. Mapping changes are
not routine local setup work; build a fresh index, verify it, and switch
`OPENSEARCH_INDEX_NAME` only as an explicit operator action.

Monitoring only:

```bash
COMPOSE_PROFILES=monitoring docker compose up --build -d
```

Monitoring URLs:
- Prometheus: `http://localhost:9090/targets`
- Grafana: `http://localhost:3000/`
- Default Grafana login: `admin / admin-change-me`

## Local Development Setup
The repo now uses a root `uv` workspace for local development and CI.
Container builds also resolve from the workspace lockfile.
Use `apps/` and `packages/` paths directly.

```bash
make sync
```

Common narrower installs:

```bash
make sync-frontend
make sync-indexer
make sync-crawler
make sync-mcp
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
- `INDEXER_API_KEY`
- `CRAWLER_SERVICE_URL` and `INDEXER_API_URL` when running multiple services locally

Optional:
- `OPENAI_API_KEY` for the optional embedding backfill job
- `EMBEDDING_ENRICHMENT_ENABLED=true` to opt in to the embedding backfill job; baseline services ignore it
- `DATABASE_URL` to point services at the local PostgreSQL instance

### Running Services
Use separate terminals:

```bash
uv run --package web-search-frontend uvicorn web_search_frontend.api.main:app --reload --port 8083
```

```bash
uv run --package web-search-indexer uvicorn web_search_indexer.main:app --reload --port 8081
```

```bash
uv run --package web-search-crawler uvicorn web_search_crawler.main:app --reload --port 8082
```

## Linting and Formatting

The preferred local CI entrypoints are the `Makefile` targets:

```bash
make ci
make ci-frontend
make ci-packages
make ci-crawler
make ci-indexer
make ci-mcp
```

You can still run the underlying tools directly when needed:

```bash
ruff check apps/frontend/src/ packages/contracts/src/ packages/core/src/ packages/postgres/src/ packages/kernel/src/ packages/opensearch/src/ packages/indexing/src/ packages/search-config/src/ apps/crawler/src/ apps/indexer/src/
ruff format apps/frontend/src/ packages/contracts/src/ packages/core/src/ packages/postgres/src/ packages/kernel/src/ packages/opensearch/src/ packages/indexing/src/ packages/search-config/src/ apps/crawler/src/ apps/indexer/src/
```

## Pre-commit Hooks

Install pre-commit hooks to catch lint and test failures before pushing:

```bash
uv run pre-commit install
```

This runs `ruff` (lint + format) and service-specific `pytest` on every commit.

## Running Tests
Tests are split by service.
Shared `pytest` and `ruff` defaults now live in the root `pyproject.toml`.

Preferred entrypoints:

```bash
make ci
make ci-frontend
make ci-packages
make ci-crawler
make ci-indexer
make ci-mcp
```

Direct test commands:

```bash
pytest packages/core/tests packages/search-config/tests packages/postgres/tests packages/kernel/tests packages/opensearch/tests
pytest apps/frontend/tests
pytest apps/indexer/tests
pytest apps/crawler/tests
```

## Deployment Overview

Use [deployment.md](./deployment.md) for the public production deployment
overview. Host-specific deployment commands and operational runbooks are not
part of the local setup guide.
