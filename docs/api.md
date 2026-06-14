# API Reference

## Status

Current minimal runtime reference.

This document intentionally covers only the API surface that is stable enough
to be useful as documentation. Fast-changing internal endpoints
should be read from the implementation when needed.

## Related Docs

- [Documentation Guide](./README.md)
- [Architecture](./architecture.md)
- [Setup Guide](./setup.md)
- [Deployment Guide](./deployment.md)

## Services

- Frontend: `http://localhost:8083`
- Indexer: `http://localhost:8081`
- Crawler: `http://localhost:8082`

API routes are not version-prefixed.

## Frontend

### `GET /search-results`

Primary search endpoint.

Current behavior:

- retrieval is BM25-based
- query operators such as `site:`, quoted phrases, and negation are supported
- successful responses may include transparency metadata such as
  `published_at`, `page_rank`, `domain_rank`, and
  other document signals when available

Use [search-ranking-policy.md](./search-ranking-policy.md) and
[search-signals.md](./search-signals.md) for ranking and signal semantics.

### `GET /indexed-documents`

Returns the public search index representation.

Current response:

```json
{
  "documents": {
    "total": 123456
  }
}
```

### `GET /health`

Simple liveness check. Returns `{"status":"ok"}`.

### `GET /readyz`

Frontend readiness check.

Current checks:

- database
- crawler connectivity
- OpenSearch status

Database health is readiness-gating. Crawler and OpenSearch are reported for
operator visibility.

## Indexer

### `POST /indexing-jobs`

Queues a crawled page for asynchronous indexing.

This is the main crawler-to-indexer handoff boundary.

### `GET /health`

Simple liveness check.

### `GET /readyz`

Indexer readiness check.

Current readiness is database-based.

## Crawler

### `GET /health`

Simple liveness check.

### `GET /readyz`

Crawler readiness check.

Current readiness is database-based.

## Source Of Truth Rule

If this document conflicts with the implementation, the implementation wins.
This file is intentionally small so that it can remain accurate.
