# Setup Guide

## Prerequisites

*   **Docker & Docker Compose**: Recommended for running the full stack (Redis + App).
*   **Python 3.10+**: For local development.
*   **Git**: For version control.

## Docker Setup (Recommended for Usage)

The easiest way to run the search engine is via Docker Compose.

1.  **Clone the repository**:
    ```bash
    git clone <repository_url>
    cd web-search
    ```

2.  **Start Services**:
    ```bash
    docker compose up --build -d
    ```
    This starts:
    *   `web_app`: The FastAPI server (Port 8080).
    *   `crawler`: The background crawl worker.
    *   `redis`: The URL frontier.

3.  **Access the App**:
    *   Search UI: http://localhost:8080
    *   API Docs: http://localhost:8080/docs

## Local Development Setup

If you want to modify the code, running locally is better.

### 1. Environment Setup

Create a virtual environment:
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate
```

Install dependencies:
```bash
# Install package in editable mode with dev dependencies (if any)
pip install -e .
pip install -r requirements.txt
```

### 2. Configuration (.env)

Copy the example configuration:
```bash
cp .env.example .env
```
Ensure `REDIS_URL` points to a running Redis instance (e.g., `localhost:6379` if running Redis via Docker).

### 3. Running Services (Manually)

You need to run the components in separate terminals:

**Terminal 1: Redis**
```bash
docker run -p 6379:6379 redis
```

**Terminal 2: Web Server**
```bash
uvicorn web_search.api.main:app --reload --port 8080
```

**Terminal 3: Crawler**
```bash
python -m web_search.crawler.scheduler
```

## Running Tests

```bash
pytest
```
