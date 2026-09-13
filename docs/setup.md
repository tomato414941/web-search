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
COMPOSE_PROFILES=
OPENROUTER_API_KEY=your-api-key
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

OpenSearch 2.19.6 is a required Compose service. Set a valid `OPENROUTER_API_KEY`
for both indexing and query embeddings. Both call OpenRouter's embeddings endpoint
with `perplexity/pplx-embed-v1-0.6b`. Sample indexing and searches make paid
embedding requests. The service does not have a keyword-only fallback.

Container images include the pinned Perplexity tokenizer and load it offline.
Direct Python runs download that tokenizer from Hugging Face on first use;
the embedding model itself runs at the API provider.

## Put sample documents into a fresh local database

The following writes synthetic documents into the local database.
Run it only against a disposable development dataset.

```bash
docker compose -f docker-compose.yml -f deploy/compose.host.yml \
  exec indexer web-search-inject-dummy-data --count 50
docker compose -f docker-compose.yml -f deploy/compose.host.yml \
  run --rm search-projection-rebuild
```

The injection command writes PostgreSQL only. The second command generates
embeddings and makes those pages searchable. OpenSearch visibility can lag briefly after a bulk write.

```bash
curl --get 'http://localhost:8083/search-results' --data-urlencode 'q=Python'
```

Check that the response has hits and `mode: "hybrid"`. Index consistency
can also be sampled with:

```bash
docker compose -f docker-compose.yml -f deploy/compose.host.yml \
  exec indexer web-search-verify-opensearch --sample-size 20
```

The verifier compares all stored-document counts with OpenSearch. On a real
corpus, intentional index exclusions can cause a mismatch; it is a diagnostic,
not proof of search quality.

To enable crawling, set `COMPOSE_PROFILES=crawler` and the `R2_*` settings listed
in `.env.example`, using a development bucket and its own credentials. The same
`up` command starts both the crawler and the automatic `link-archive` worker.
The R2 key needs object read/write access to that private bucket. An empty frontier
does not fetch anything by itself; URL admission and frontier refill are separate
operator operations. `web-search-link-archive status` in the archive container
reports pending uploads and the current snapshot; its logs report retries.

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
export OPENROUTER_API_KEY=your-api-key
export OPENSEARCH_URL='http://localhost:9200'
export OPENSEARCH_INDEX_NAME=documents-hybrid-v2
export INDEXER_API_URL='http://localhost:8081/documents'
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
`make ci-mcp`, or `make ci-hybrid` for a focused change. `docs/deployment.md` covers production
verification and index replacement; neither is an implicit part of local setup.
