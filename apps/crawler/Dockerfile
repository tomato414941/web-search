# Crawler Service Dockerfile
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Copy workspace metadata and source
COPY pyproject.toml uv.lock ./
COPY apps/crawler/pyproject.toml ./apps/crawler/pyproject.toml
COPY packages/contracts/pyproject.toml ./packages/contracts/pyproject.toml
COPY packages/core/pyproject.toml ./packages/core/pyproject.toml
COPY packages/postgres/pyproject.toml ./packages/postgres/pyproject.toml
COPY packages/web-knowledge/pyproject.toml ./packages/web-knowledge/pyproject.toml
COPY packages/search-config/pyproject.toml ./packages/search-config/pyproject.toml
COPY packages/search-telemetry/pyproject.toml ./packages/search-telemetry/pyproject.toml
COPY apps/crawler/src/ ./apps/crawler/src/
COPY packages/contracts/src/ ./packages/contracts/src/
COPY packages/core/src/ ./packages/core/src/
COPY packages/postgres/src/ ./packages/postgres/src/
COPY packages/web-knowledge/src/ ./packages/web-knowledge/src/
COPY packages/search-config/src/ ./packages/search-config/src/
COPY packages/search-telemetry/src/ ./packages/search-telemetry/src/

# Build a production venv for the crawler package
RUN uv sync --frozen --package web-search-crawler --no-dev --no-editable

# Stage 2: Production image
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /root/.cache

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -m appuser

WORKDIR /app

# Copy the prebuilt virtualenv from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code and config
COPY config/ ./config/
COPY db/ ./db/

ENV PATH=/app/.venv/bin:$PATH \
    VIRTUAL_ENV=/app/.venv \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN mkdir -p /data && chown appuser:appuser /data

# Expose API port
EXPOSE 8000

USER appuser
# Run FastAPI application
CMD ["uvicorn", "web_search_crawler.main:app", "--host", "0.0.0.0", "--port", "8000"]
