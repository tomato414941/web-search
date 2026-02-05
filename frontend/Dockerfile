# Frontend Service Dockerfile
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy shared package first (for dependency resolution)
COPY shared/ ./shared/

# Copy and install dependencies
COPY frontend/requirements.txt .
RUN pip install --no-cache-dir --user -e ./shared \
    && pip install --no-cache-dir --user -r requirements.txt gunicorn

# Stage 2: Production image
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /root/.cache

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
COPY --from=builder /app/shared ./shared

# Ensure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY frontend/src/ ./src/
COPY frontend/gunicorn.conf.py .

ENV PORT=8000 HOST=0.0.0.0 SEARCH_DB=/data/search.db \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

EXPOSE 8000

CMD ["gunicorn", "-c", "gunicorn.conf.py", "frontend.api.main:app"]
