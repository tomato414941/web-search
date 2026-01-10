# Indexer Service Dockerfile (Based on Frontend)
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy shared package first (for dependency resolution)
COPY shared/ ./shared/

# Copy and install dependencies
COPY indexer/requirements.txt .
# Fix shared library path: ../shared -> ./shared (as we copied it to /app/shared)
RUN sed -i 's|\.\./shared|\./shared|g' requirements.txt
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Production image
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /root/.cache

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
COPY --from=builder /app/shared ./shared

# Ensure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY indexer/src/ ./src/

ENV PORT=8081 HOST=0.0.0.0 SEARCH_DB=/data/search.db \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

EXPOSE 8081

# Use Uvicorn for Indexer (API-based, less static serving needs than Frontend)
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]
