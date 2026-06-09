# Web model maintenance image.
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
COPY packages/web-model/pyproject.toml ./packages/web-model/pyproject.toml
COPY packages/core/pyproject.toml ./packages/core/pyproject.toml
COPY packages/postgres/pyproject.toml ./packages/postgres/pyproject.toml
COPY packages/web-model/src/ ./packages/web-model/src/
COPY packages/core/src/ ./packages/core/src/
COPY packages/postgres/src/ ./packages/postgres/src/

RUN uv sync --frozen --package web-search-web-model --no-dev --no-editable

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /root/.cache

RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -m appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH=/app/.venv/bin:$PATH \
    VIRTUAL_ENV=/app/.venv \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

USER appuser

CMD ["python", "-m", "web_search_web_model.worker"]
