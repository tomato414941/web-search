# Setup Guide

## Prerequisites

*   **Docker & Docker Compose**: Recommended for production-like environments.
*   **Python 3.10+**: For local development.
*   **Git**: For version control.

## Docker Setup (Recommended)

The easiest way to run the full search engine is via Docker Compose.

1.  **Clone and Start**:
    ```bash
    git clone <repository_url>
    cd web-search
    docker compose -f deployment/frontend/docker-compose.yml up --build -d
    # Note: Crawler service might need its own compose file if deploying distributedly
    ```

    This starts:
    *   `frontend` (Web Node): http://localhost:8080
    *   `indexer` (Write Node): http://localhost:8081
    *   `crawler` (Worker Node): Background service.
    *   `redis`: URL Frontier (Internal).

## Local Development Setup

For development, you run services individually. This project uses a **Folder-Separated Monorepo** structure.

### 1. Environment Setup

Create a virtual environment and install dependencies.

```bash
# Create venv
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 1. Install Shared Library (Editable Mode) - CRITICAL
pip install -e shared

# 2. Install Service Dependencies
pip install -r frontend/requirements.txt
pip install -r indexer/requirements.txt
pip install -r crawler/requirements.txt
```

### 2. Configuration (.env)

Copy example configurations:

```bash
# Frontend
cp frontend/.env.example frontend/.env

# Indexer
cp indexer/.env.example indexer/.env

# Crawler
cp crawler/.env.example crawler/.env
```

Ensure `REDIS_URL` in `crawler/.env` points to your local Redis.
Ensure `OPENAI_API_KEY` is set in `indexer/.env` and `frontend/.env` if you want semantic search.

### 3. Running Services (Manually)

You need 4 terminals.

**Terminal 1: Redis**
```bash
docker run -p 6379:6379 redis:alpine
```

**Terminal 2: Frontend (Search Cluster)**
```bash
cd frontend/src
uvicorn frontend.api.main:app --reload --port 8080
# Access at http://localhost:8080
```

**Terminal 3: Indexer (Write Cluster)**
```bash
cd indexer/src
uvicorn app.main:app --reload --port 8081
# Access at http://localhost:8081
```

**Terminal 4: Crawler (Worker)**
```bash
cd crawler/src
python -m app.main
```

## Running Tests

Tests are split by service.

```bash
# Test Shared Library
pytest shared/tests

# Test Frontend
pytest frontend/tests

# Test Indexer
pytest indexer/tests

# Test Crawler
pytest crawler/tests
```
