# Deployment Guide

## Status

Current deployment and release reference.

## Related Docs

- [Documentation Guide](./README.md)
- [Setup Guide](./setup.md)
- [Architecture](./architecture.md)

## Scope

This guide covers the production deployment model.
It does not replace the local setup flow in [setup.md](./setup.md).

## Current Deployment Model

- Runtime is direct `docker compose` + `Caddy` on a dedicated Hetzner host.
- PRD host: environment-specific dedicated production host.
- Repo path on PRD: environment-specific host-local repository path.
- Only `frontend` is exposed publicly; `indexer`, `crawler`, and data services stay on the private compose network.

Core deployment files:
- `docker-compose.yml`: base service graph
- `deploy/compose.host.yml`: binds `frontend` to `127.0.0.1:${FRONTEND_PORT}`
- `deploy/compose.prd-data.yml`: reuses existing production data volumes and keeps OpenSearch data on the PRD root disk (`WEB_SEARCH_PRD_OPENSEARCH_DATA_DIR`, default `/var/lib/web-search/opensearch-data`)
- `deploy/Caddyfile.prd`: PRD reverse proxy

Environment file on host:
- Production deployments read a host-local env file outside the repository.
- The exact path is environment-specific.

## CI and Direct Deployment

The current release flow is `main`-based source deployment on the production
host.

### Branch Policy

- `main` is the only active release branch.
- `main` is the source of truth for application code, compose definitions, and promotion inputs.
- Routine personal-development changes are pushed directly to `main`.
- Use a short-lived branch only when a change is large, risky, or explicitly needs external review.

### CI

- `CI/CD Pipeline` runs on pushes to `main`.
- It executes path-aware lint and test jobs.

### Production Deployment

- Normal entrypoint: `CONFIRM_PRD_DEPLOY=1 make deploy-prd PRD_REF=main`
- Deploy settings are provided by the operator environment.
- Production runtime secrets remain in the host-local env file outside the repository.
- `deploy-prd` runs `docker compose up -d --build --remove-orphans` through `scripts/ops/deploy_compose.sh`.
- Run deploy verification immediately after deployment.

### Admin Verification Intent

`verify_compose_admin_pages.sh` validates cold admin page loads after deploy,
not just a warm-cache happy path.

- It logs in through `/admin/login` and then loads the main admin pages.
- It should pass even immediately after a frontend restart.
- A failure here usually means the admin request path became too heavy again, or the deploy-time client path regressed.
- This check assumes admin pages read explicit read models or snapshots rather than rebuilding heavy state inline during the request.

The production workflow uses a looser threshold than local smoke checks because
it validates the real deploy-time cold path on the PRD host.

### Verification Order

Run CI before production deployment, then verify PRD immediately after deploy.

## Runtime Topology

Default always-on services:
- `frontend`: public production domain
- `indexer`: private (internal network only)
- `indexer-worker`: private (internal network only)
- `indexer-maintenance-worker`: private (internal network only)
- `postgres`: private (internal network only)

Optional profiles:
- `search`: starts `opensearch` when you need to validate search retrieval.
- `search-backfill`: runs `opensearch-backfill` as a temporary one-off job when you explicitly need a rebuild.
- `crawler`: starts `crawler` when you need crawl flow validation.
- `embedding`: runs `embedding-backfill` for one-off optional embedding-enrichment backfills. It requires `EMBEDDING_ENRICHMENT_ENABLED=true`.
- `monitoring`: starts `prometheus` and `grafana` for temporary observability windows.
  - Monitoring services are intentionally best-effort. They keep their own healthchecks, but they should not block the core app deployment if Prometheus needs extra time to settle.

## Host Setup Summary

1. Install Docker Engine with Compose plugin and Caddy on the target host.
2. Clone the repository to the host-local deployment path.
3. Create the host-local environment file outside the repository.
4. Install `deploy/Caddyfile.prd`.
5. Start or update the stack with:

```bash
CONFIRM_PRD_DEPLOY=1 make deploy-prd PRD_REF=main
```

## Required Environment Variables
Set these in the host-local env file used by the production deployment.

| Variable | Example | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | `production` | Production runtime behavior. |
| `POSTGRES_PASSWORD` | `change-me-strong` | Use a unique strong password. |
| `ADMIN_USERNAME` | `admin` | Admin login user. |
| `ADMIN_PASSWORD` | `change-me` | Admin credential. |
| `ADMIN_SESSION_SECRET` | `change-me-long-random` | 32+ chars random string. |
| `ALLOWED_HOSTS` | `palebluesearch.com,frontend` | Include the production domain and the internal `frontend` hostname for Prometheus scraping. |
| `ANALYTICS_SALT` | `change-me-random` | Random salt for analytics hashing. |
| `INDEXER_API_KEY` | `change-me-random` | Shared secret between frontend, crawler, and indexer. |
| `OPENAI_API_KEY` | `` | Optional credential for the explicit embedding backfill profile. Baseline services do not need it. |
| `EMBEDDING_ENRICHMENT_ENABLED` | `false` | Explicit opt-in for the one-off embedding backfill job. Baseline ingestion and BM25 search ignore it. |
| `OPENSEARCH_ENABLED` | `false` | Keep `false` for the lightweight default runtime. Set `true` only when `search` profile is enabled. |
| `COMPOSE_PROFILES` | `` | Empty by default. Use `search`, `crawler`, `monitoring`, or a temporary combination such as `crawler,search` only for targeted validation windows. |
| `PROMETHEUS_PORT` | `9091` | Used only when `monitoring` profile is enabled. Choose a host-local port that does not conflict with other apps. |
| `GRAFANA_PORT` | `3001` | Used only when `monitoring` profile is enabled. Choose a host-local port that does not conflict with other apps. |
| `GRAFANA_ADMIN_PASSWORD` | `change-me-monitoring` | Required when `monitoring` profile is enabled. |
| `POSTGRES_MAX_CONNECTIONS` | `64` | Keeps DB connection budget explicit on the host. |
| `DB_POOL_MAX_FRONTEND` | `4` | Frontend DB pool budget. |
| `DB_POOL_MAX_INDEXER` | `6` | Indexer DB pool budget. |
| `DB_POOL_MAX_INDEXER_WORKER` | `8` | Job-worker DB pool, sized for the conservative async defaults. |
| `DB_POOL_MAX_INDEXER_MAINTENANCE` | `2` | Maintenance worker only needs a small pool. |
| `DB_POOL_MAX_CRAWLER` | `4` | Used only when `crawler` profile is enabled. |
| `DB_EXECUTOR_MAX_CRAWLER` | `6` | Caps crawler blocking DB calls below the DB pool so health/admin/worker paths keep connection headroom. |
| `CRAWL_CONCURRENCY_CRAWLER` | `2` | Conservative crawler concurrency for temporary crawler test windows. Increase only after crawler health stays responsive. |
| `CRAWL_AUTO_START_CRAWLER` | `false` | Keep `false` by default so crawler runs only in explicit validation windows. |
| `INDEXER_JOB_WORKERS` | `1` | Conservative async index worker count. |
| `INDEXER_JOB_BATCH_SIZE` | `10` | Max claimed jobs per poll. |
| `INDEXER_JOB_CONCURRENCY` | `2` | Per-process async job concurrency. |
| `INDEXER_JOB_LEASE_SEC` | `120` | Job lease duration. |
| `INDEXER_JOB_MAX_RETRIES` | `5` | Retry cap before permanent failure. |
| `INDEXER_JOB_POLL_INTERVAL_MS` | `500` | Worker poll interval. |
| `INDEXER_JOB_RETRY_BASE_SEC` | `5` | Exponential retry base. |
| `INDEXER_JOB_RETRY_MAX_SEC` | `1800` | Exponential retry ceiling. |

Resource budget defaults:
- DB pool minimum stays at `1` per service to avoid preallocating idle PostgreSQL connections.
- Always-on DB pool max budget is `20` (`frontend 4 + indexer 6 + jobs 8 + maintenance 2`).
- Enabling the optional crawler raises the DB pool max budget to `24`.
- Default memory caps are `frontend 384m`, `indexer 384m`, `indexer-worker 768m`, `indexer-maintenance-worker 256m`, `crawler 384m`, `postgres 768m`.
- Enabling `monitoring` adds `prometheus 256m` and `grafana 256m` by default.

## Backup and Restore

Production and local Docker Compose runs both use PostgreSQL.

Create a PostgreSQL dump from the running container:

```bash
BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
docker exec -t web-search-postgres pg_dump -U websearch websearch \
  > "$BACKUP_DIR/websearch_$TIMESTAMP.sql"
```

Restore a PostgreSQL dump into the container:

```bash
cat /backups/websearch_YYYYMMDD_HHMMSS.sql | \
  docker exec -i web-search-postgres psql -U websearch websearch
```

## Release Flow

### Deploy to PRD

1. Ensure the compose definitions you want are on `main`.
2. Wait for `CI/CD Pipeline` to succeed.
2. Deploy the tested ref with explicit confirmation:

```bash
CONFIRM_PRD_DEPLOY=1 make deploy-prd PRD_REF=main
```

3. Confirm the actual PRD host state:

```bash
./scripts/ops/verify_compose_deploy.sh prd main
./scripts/ops/verify_compose_admin_pages.sh prd 10
```

## Admin Dashboard Constraints

The admin dashboard is an operations summary, not an ad-hoc analytics page.

- `/admin/` must stay fast on a cold request after deploy.
- The request path must not depend on synchronous full-table scans over `documents`, `frontier_entries`, or `crawl_logs`.
- Heavy frontier state should come from persisted counters or snapshots.
- Dashboard cache rebuild must be single-flight across frontend workers.
- If a new metric needs a large scan or rollup, move it to a dedicated analytics page or a background snapshot job.

## Initial Validation Checklist
Run these checks right after deployment.

### 1) Service health
- Open `https://palebluesearch.com/health`
- Expect JSON: `{"status":"ok"}`

### 2) Admin login
- Open `https://palebluesearch.com/admin/login`
- Login with admin credentials.

### 3) Async index queue behavior
Use any HTTP client from a trusted network path to the indexer service (for example, inside the frontend container or via internal curl):

```bash
curl -sS -X POST "http://indexer:8000/api/v1/indexer/page" \
  -H "X-API-Key: $INDEXER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","title":"Example","content":"Example content","outlinks":[]}'
```

Expected response:
- HTTP `202`
- includes `job_id`

Check job status:

```bash
curl -sS "http://indexer:8000/api/v1/indexer/jobs/<job_id>" \
  -H "X-API-Key: $INDEXER_API_KEY"
```

Expected progression:
- `pending` -> `processing` -> `done`
- Failure path: `failed_retry` then `failed_permanent`

Automation (same checks in one command):

```bash
./scripts/ops/run_compose_smoke_via_frontend.sh prd
```

### 4) Optional: search validation
Enable `COMPOSE_PROFILES=search` and set `OPENSEARCH_ENABLED=true`, then redeploy.

- Confirm `GET /readyz` reports `opensearch.status = ok`
- Re-run the smoke command above
- Search from frontend UI and confirm indexed documents appear

If you need to rebuild OpenSearch from PostgreSQL, enable `COMPOSE_PROFILES=search,search-backfill` only for that maintenance window, then remove `search-backfill` again after the one-off job finishes.

### 5) Optional: crawl -> index validation
Enable `COMPOSE_PROFILES=crawler,search` only for the test window, then redeploy.

- Open `/admin/crawlers`
- Start crawler manually
- Admit a known URL from the admin frontier UI
- Confirm crawler history shows `submitted`
- Stop the crawler after validation
- Clear `COMPOSE_PROFILES` again when finished

### 6) Optional: monitoring validation
Enable `COMPOSE_PROFILES=monitoring`, then redeploy.

- Confirm inside the server:
  - `curl -s http://127.0.0.1:<PROMETHEUS_PORT>/targets`
  - `curl -s http://127.0.0.1:<GRAFANA_PORT>/api/health`
- Use SSH port-forwarding from your workstation:

```bash
ssh -L 3001:127.0.0.1:3001 -L 9091:127.0.0.1:9091 <prd-ssh-host>
```

- Open `http://localhost:3001`
- Login with `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`
- Confirm the provisioned `Web Search Overview` dashboard is visible

## Rollout Safety Notes
- Never reuse production DB or secrets.
- Keep `apps/indexer` and `apps/crawler` private; expose only `apps/frontend` publicly.
- Keep `COMPOSE_PROFILES` empty by default.
- Only enable `crawler` / `search` / `search-backfill` / `monitoring` profiles for short validation windows.
- Tune `INDEXER_JOB_WORKERS` and `CRAWL_CONCURRENCY` gradually while watching frontier growth.

## Rollback Procedure
Use this if an environment becomes unhealthy after a deploy.

1. Identify the last known-good commit SHA.
2. Clear `COMPOSE_PROFILES` first unless the failing test explicitly needs them.
3. If frontier pressure is high, set conservative worker values:
   - `INDEXER_JOB_WORKERS=1`
   - `INDEXER_JOB_CONCURRENCY=1`
   - `CRAWL_CONCURRENCY=2`
4. Redeploy:

```bash
CONFIRM_PRD_DEPLOY=1 make deploy-prd PRD_REF=<last_good_sha>
```

5. Verify:
   - `GET /health` is `200`
   - `pending_jobs` is no longer increasing indefinitely
6. If rollback fails, stop and investigate before attempting another production deploy.
