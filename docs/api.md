# API Reference

## Status

Current minimal runtime reference.

This document intentionally covers only the API surface that is stable enough
to be useful as documentation. Fast-changing internal and admin endpoints
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

The shared JSON API prefix is `/api/v1`.

## Frontend

### `GET /api/v1/search`

Primary search endpoint.

Current behavior:

- retrieval is BM25-based
- query operators such as `site:`, quoted phrases, and negation are supported
- API key auth is optional
- successful responses may include transparency metadata such as
  `published_at`, `temporal_anchor`, `authorship_clarity`, `factual_density`,
  `origin_score`, `origin_type`, `page_rank`, `domain_rank`, and other
  document signals when available

Use [search-ranking-policy.md](./search-ranking-policy.md) and
[search-signals.md](./search-signals.md) for ranking and signal semantics.

### `POST /api/v1/search/click`

Logs a click event tied to a prior search response.

### `GET /api/v1/quality/summary`

Search analytics summary endpoint.

This is an analytics surface, not the source of truth for ranking evaluation.
Use [search-evaluation.md](./search-evaluation.md) for evaluation policy.

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

### `POST /api/v1/indexer/page`

Queues a crawled page for asynchronous indexing.

This is the main crawler-to-indexer handoff boundary.

### `GET /api/v1/indexer/jobs/{job_id}`

Returns asynchronous indexing job status.

### `GET /api/v1/indexer/stats`

Returns indexer statistics and job queue metrics.

### `GET /health`

Simple liveness check.

### `GET /readyz`

Indexer readiness check.

Current readiness is database-based.

## Crawler

### `POST /api/v1/urls`

Admits URLs into the frontier.

### `POST /api/v1/crawl-now`

Immediately fetches a single URL and submits it to the indexer.

### `GET /api/v1/worker/status`

Returns crawler worker lifecycle state and volatile in-memory task status.

### `GET /api/v1/history`

Returns raw crawl-attempt history from `crawl_logs`.

### `GET /api/v1/history/admin`

Returns the operator-facing history read model used by admin pages.

### `GET /health`

Simple liveness check.

### `GET /readyz`

Crawler readiness check.

Current readiness is database-based.

## Source Of Truth Rule

If this document conflicts with the implementation, the implementation wins.
This file is intentionally small so that it can remain accurate.
