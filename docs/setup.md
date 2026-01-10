# Setup Guide

## Prerequisites

*   **Docker & Docker Compose**: Recommended for production-like environments.
*   **Python 3.10+**: For local development.
*   **Git**: For version control.
*   **Lightsail / VPS**: (Optional) For distributed deployment.

## Docker Setup (Recommended)

The easiest way to run the full search engine is via Docker Compose.

1.  **Clone and Start**:
    ```bash
    git clone <repository_url>
    cd web-search
    docker compose up --build -d
    ```

    This starts:
    *   `frontend` (Web Node): http://localhost:8080
    *   `crawler` (Worker Node): Background service.
    *   `redis`: URL Frontier (Internal).

## Local Development Setup

For development, you run services individually. This project uses a **Folder-Separated Monorepo** structure.

### 1. Environment Setup

Create a virtual environment and install the Common Library (`shared`) and service dependencies.

```bash
# Create venv
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 1. Install Shared Library (Editable Mode) - CRITICAL
pip install -e shared

# 2. Install Frontend Dependencies
pip install -r frontend/requirements.txt

# 3. Install Crawler Dependencies
pip install -r crawler/requirements.txt
```

### 2. Configuration (.env)

The project uses separate `.env` files for each service, but efficient local dev often shares one or uses defaults.
For simplicity, copy the examples:

```bash
# Frontend
cp deployment/frontend/.env.example frontend/.env

# Crawler
cp deployment/crawler/.env.example crawler/.env
```

Ensure `REDIS_URL` in `crawler/.env` points to your local Redis (e.g., `redis://localhost:6379/0`).

> [!NOTE]
> When running services manually with `python -m`, variables in `.env` files are **not automatically loaded**. You must export them in your shell or use a tool like `python-dotenv`.


### 3. Running Services (Manually)

You need 3 terminals.

**Terminal 1: Redis**
```bash
docker run -p 6379:6379 redis:alpine
```

**Terminal 2: Frontend (Web API & UI)**
```bash
cd frontend/src
python -m frontend.api.main
# Access at http://localhost:8080
```

**Terminal 3: Crawler (Worker)**
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

# Test Crawler
pytest crawler/tests
```
