# Deployment Guide

This directory contains the files needed for production deployment.

## Structure

```
deployment/
├── README.md               # This file
├── .gitignore             # Git ignore patterns
├── frontend/              # Search Cluster (Front + Indexer)
│   ├── .env.example       # Shared environment variables
│   └── docker-compose.yml # Orchestrator (Frontend, Indexer, Redis)
└── crawler/               # Crawler Server
    ├── .env.example       # Crawler Config
    └── docker-compose.yml # Crawler only
```

## Deployment Steps

### 1. Search Cluster (Frontend + Indexer)

This composes the "Core" of the search engine.

```bash
# Clone the repository
git clone https://github.com/tomato414941/web-search.git
cd web-search/deployment/frontend

# Create environment file
cp .env.example .env

# Edit environment variables (required)
nano .env
# ADMIN_PASSWORD=...
# ADMIN_SESSION_SECRET=...
# INDEXER_API_KEY=...
# OPENAI_API_KEY=...

# Pull Docker images
docker pull ghcr.io/tomato414941/web-search:latest
docker pull ghcr.io/tomato414941/web-search-indexer:latest

# Start containers
docker compose up -d

# View logs
docker compose logs -f
```

### 2. Crawler Server (Worker)

Only needed if deploying distributed workers on separate machines.

```bash
# Clone the repository
cd web-search/deployment/crawler

# Create environment file
cp .env.example .env

# Configure Connection to Search Cluster
nano .env
# FRONTEND_IP=<Search Cluster IP>
# CRAWLER_SERVICE_URL=http://<Crawler IP>:8000
# INDEXER_API_KEY=<Same key as Search Cluster>

# Pull Docker image
docker pull ghcr.io/tomato414941/web-search-crawler:latest

# Start containers
docker compose up -d
```

## Environment Variables

See `.env.example` in each directory.

### Key Variables

*   `ADMIN_SESSION_SECRET`: Must match between `.env` and `frontend`.
*   `INDEXER_API_KEY`: Must match between `frontend/.env` (Search Cluster) and `crawler/.env`.
*   `OPENAI_API_KEY`: Required for semantic search (used by Indexer and Frontend).

## Update Procedure

```bash
# Pull latest code
git pull

# Pull latest Docker images
docker pull ghcr.io/tomato414941/web-search:latest
docker pull ghcr.io/tomato414941/web-search-indexer:latest

# Recreate containers
docker compose up -d --force-recreate
```
