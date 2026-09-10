# Local development

## Start a searchable stack

Run from the repository root with Docker and Docker Compose installed. For a
fresh checkout, create a local environment file:

```bash
cp .env.example .env
```

Set these values in `.env` before starting services:

```dotenv
ENVIRONMENT=development
POSTGRES_PASSWORD=local-development-password
INDEXER_API_KEY=local-development-key
COMPOSE_PROFILES=search
OPENSEARCH_ENABLED=true
FRONTEND_PORT=8083
```

These are local example values. Use separate operator-managed values in
production. Compose constructs the services' `DATABASE_URL` from the PostgreSQL
settings and supplies their internal service addresses.

```bash
docker compose -f docker-compose.yml -f deploy/compose.host.yml up --build -d
```

The host overlay publishes only the frontend, on localhost. The search UI is at
`http://localhost:8083/`, and OpenAPI is at `http://localhost:8083/docs`.
PostgreSQL, OpenSearch, and the indexer remain inside the Compose network.

The `search` profile starts OpenSearch; `OPENSEARCH_ENABLED=true` makes the
frontend and indexer use it. Both are required. Initial startup can race with
OpenSearch initialization; the frontend retries its client setup on subsequent
search requests. Inspect `docker compose ps` and `/readyz` if search is degraded.
Readiness HTTP 200 alone does not establish that OpenSearch is available.

## Put sample documents into a fresh local database

The following writes synthetic documents and links into the local database.
Run it only against a disposable development dataset.

```bash
docker compose -f docker-compose.yml -f deploy/compose.host.yml \
  exec indexer web-search-inject-dummy-data --count 50
docker compose -f docker-compose.yml -f deploy/compose.host.yml \
  run --rm search-projection-rebuild
```

The injection command writes PostgreSQL only. The second command makes those
pages searchable. OpenSearch visibility can lag briefly after a bulk write.

```bash
curl --get 'http://localhost:8083/search-results' --data-urlencode 'q=Python'
```

Check that the response has hits and is not marked `degraded`. Index consistency
can also be sampled with:

```bash
docker compose -f docker-compose.yml -f deploy/compose.host.yml \
  exec indexer web-search-verify-opensearch --sample-size 20
```

The verifier compares all stored-document counts with OpenSearch. On a real
corpus, intentional index exclusions can cause a mismatch; it is a diagnostic,
not proof of search quality.

To enable crawling, set `COMPOSE_PROFILES=search,crawler` and run the same `up`
command. An empty frontier does not fetch anything by itself. URL admission and
frontier refill are separate operator operations.

## Run Python services outside containers

Use Python 3.11+ and `uv`, then run `make sync`. The narrower `make sync-frontend`,
`make sync-indexer`, `make sync-crawler`, and `make sync-mcp` targets are available.

For direct Python runs, provide a reachable PostgreSQL database and OpenSearch
instance. The base Compose stack does not publish those ports. Required settings
and local service addresses are:

```bash
export ENVIRONMENT=development
export DATABASE_URL='postgresql://websearch:local-development-password@localhost:5432/websearch'
export INDEXER_API_KEY='local-development-key'
export OPENSEARCH_ENABLED=true
export OPENSEARCH_URL='http://localhost:9200'
export OPENSEARCH_INDEX_NAME=documents
export INDEXER_API_URL='http://localhost:8081/documents'
export CRAWLER_SERVICE_URL='http://localhost:8082'
```

`DATABASE_URL` is required, not optional. `INDEXER_API_KEY` is required by the
indexer and crawler, not the frontend. Direct Python runs must use addresses
reachable from the host; Compose supplies different internal addresses.

Apply database migrations once before starting services:

```bash
uv run --package web-search-postgres python -c 'from web_search_postgres.migrate import migrate; migrate()'
```

Run each service in its own terminal:

```bash
uv run --package web-search-frontend uvicorn web_search_frontend.api.main:app --port 8083
uv run --package web-search-indexer uvicorn web_search_indexer.main:app --port 8081
uv run --package web-search-crawler uvicorn web_search_crawler.main:app --port 8082
```

## Checks

```bash
make ci
uv run pre-commit install
```

Use `make ci-frontend`, `make ci-indexer`, `make ci-crawler`, `make ci-packages`,
or `make ci-mcp` for a focused change. `docs/deployment.md` covers production
verification and index replacement; neither is an implicit part of local setup.
