# Setup Guide

## Prerequisites
- Docker & Docker Compose (recommended)
- Python 3.11+
- Git

## Docker Setup (Recommended)
Run the full stack with Docker Compose:

```bash
docker compose up --build -d
```

Services and ports:
- Frontend (UI + Search API): http://localhost:8080
- Indexer (Write API): http://localhost:8081
- Crawler (API): http://localhost:8082
- PostgreSQL: internal to the compose network

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
uvicorn frontend.api.main:app --reload --port 8080
```

```bash
export PYTHONPATH=indexer/src
uvicorn app.main:app --reload --port 8081
```

```bash
export PYTHONPATH=crawler/src
uvicorn app.main:app --reload --port 8082
```

## Running Tests
Tests are split by service.

```bash
pytest shared/tests
pytest frontend/tests
pytest indexer/tests
pytest crawler/tests
```
