# Deployment Overview

## Status

Current public deployment reference.

## Scope

This document describes the deployment shape at a high level. It intentionally
does not include host-specific paths, credentials, volume names, rollback
commands, or operator-only runbooks.

For local development, use [setup.md](./setup.md).

## Model

- The production runtime is deployed with Docker Compose behind Caddy.
- Only the frontend service is exposed publicly.
- Indexer, crawler, PostgreSQL, OpenSearch, and monitoring services are private
  runtime dependencies.
- Production secrets and host-specific settings live outside the repository.
- Routine development lands directly on `main`; CI runs on pushes to `main`.
- Production deployment is an explicit operator action after CI passes.
- Deployment scripts ship a source bundle and record the deployed commit in an
  operator state file. The server-side Git checkout is for operator inspection,
  not the runtime source of truth.
- OpenSearch search projection schema changes should be applied by building a
  fresh index with the new mapping, for example `documents_v2`, then switching
  `OPENSEARCH_INDEX_NAME` after verification. The rebuild command defaults to
  `--batch-size 100`; keep that value for the production 512MiB indexer
  container. Prefer the guarded auto runner for production:

  ```bash
  WEB_SEARCH_PRD_SERVER=root@5.223.74.201 \
  make rebuild-projection-prd-auto PRD_REBUILD_ARGS="--index-name documents_v2 --state-file /srv/web-search/.maintenance/search-projection-rebuild-documents-v2.env --segment-size 10000 --max-segments 10"
  ```

  Use a separate state file per target index. The runner resumes from the saved
  `LAST_URL`, runs one segment at a time, and waits before the next segment when
  container memory crosses its configured guard.

## Compose Files

- `docker-compose.yml`: base service graph.
- `deploy/compose.host.yml`: host binding overlay.
- `deploy/compose.prd-data.yml`: production data-volume overlay.
- `deploy/Caddyfile.prd`: production reverse proxy template.

## Profiles

Optional services are enabled through Compose profiles only when needed:

- `search`: OpenSearch runtime.
- `search-projection-rebuild`: one-off search projection rebuild job.
- `crawler`: crawler API and worker runtime.
- `embedding`: one-off optional embedding enrichment job.
- `monitoring`: Prometheus and Grafana.

Keep the default runtime small. Enable optional profiles only for explicit
validation, maintenance, or observation windows.

## Verification

After production deployment, verify:

- public health endpoint returns healthy status
- readiness endpoint reports expected dependency status
- compose services converge to running or healthy state

Operator commands and host-specific values are intentionally kept out of this
public document.
