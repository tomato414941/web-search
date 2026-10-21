# Link archive worker image.
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN sed -i -E '/^mozilla\/(Comodo_AAA_Services_root|emSign_(ECC_Root_CA|Root_TLS_CA|Root_CS_CA)_-_G3)\.crt$/s/^/!/' /etc/ca-certificates.conf \
    && update-ca-certificates \
    && python -m pip install --no-cache-dir --cert /etc/ssl/certs/ca-certificates.crt --upgrade pip==26.2.2 uv==0.13.4

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

RUN sed -i -E '/^mozilla\/(Comodo_AAA_Services_root|emSign_(ECC_Root_CA|Root_TLS_CA|Root_CS_CA)_-_G3)\.crt$/s/^/!/' /etc/ca-certificates.conf \
    && update-ca-certificates \
    && python -m pip install --no-cache-dir --cert /etc/ssl/certs/ca-certificates.crt --upgrade pip==26.2.2

RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -m appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH=/app/.venv/bin:$PATH \
    VIRTUAL_ENV=/app/.venv \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

USER appuser

CMD ["web-search-link-archive", "run"]
