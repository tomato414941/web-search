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
- OpenSearch search projection schema changes require an explicit
  `search-projection-rebuild` maintenance run so existing documents receive the
  new projection fields. The rebuild command defaults to `--batch-size 100`;
  keep that value for the production 512MiB indexer container and use
  `--max-documents` plus the logged `last_url` for segmented maintenance runs.

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
