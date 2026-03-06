# Coolify Staging Setup

This guide defines a staging environment that uses the same deployment path as production on Coolify, while keeping the default runtime footprint intentionally small.

## Goal
- Use the same deployment path as production (Coolify + Docker Compose).
- Keep staging resources isolated from production.
- Keep always-on services light enough to share a host with production safely.
- Validate async indexing flow (`202 + job_id`) before production release.

## Deployment Topology

Default always-on services:
- `frontend`: public (staging domain)
- `indexer`: private (internal network only)
- `indexer-worker`: private (internal network only)
- `indexer-maintenance-worker`: private (internal network only)
- `postgres`: private (internal network only)

Optional profiles:
- `search`: starts `opensearch` and `opensearch-backfill` when you need to validate search retrieval.
- `crawler`: starts `crawler` when you need crawl flow validation.
- `embedding`: starts `embedding-backfill` for one-off embedding backfills.
- `monitoring`: starts `prometheus` and `grafana` for temporary observability windows.
  - Monitoring services are intentionally best-effort. They keep their own healthchecks, but they should not block the core app deployment if Prometheus needs extra time to settle.

## Coolify App Configuration
1. Create a separate Coolify Project for staging (for example `web-search-staging`).
2. Create a new Application from this repository.
3. Select `Docker Compose` deployment.
4. Set Compose file path to `docker-compose.yml`.
5. Set branch to staging target branch (for example `main` or `staging`).
6. Expose only `frontend` service on a public domain.
7. Leave `COMPOSE_PROFILES` empty for the default lightweight staging runtime.
8. If you enable `monitoring`, keep `PROMETHEUS_BIND_ADDRESS` and `GRAFANA_BIND_ADDRESS` on `127.0.0.1` and use SSH port-forwarding instead of exposing them publicly.

## Required Environment Variables
Set these in Coolify application environment variables.

| Variable | Example | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | `production` | Keep production-like behavior in staging. |
| `POSTGRES_PASSWORD` | `change-me-strong` | Use a unique strong password. |
| `ADMIN_USERNAME` | `admin` | Staging admin login user. |
| `ADMIN_PASSWORD` | `change-me` | Staging-only credential. |
| `ADMIN_SESSION_SECRET` | `change-me-long-random` | 32+ chars random string. |
| `ALLOWED_HOSTS` | `stg-search.example.com,frontend` | Include the staging domain and the internal `frontend` hostname for Prometheus scraping. |
| `ANALYTICS_SALT` | `change-me-random` | Random salt for analytics hashing. |
| `INDEXER_API_KEY` | `change-me-random` | Shared secret between crawler/frontend and indexer. |
| `OPENAI_API_KEY` | `` | Optional. Leave empty to disable embeddings. |
| `OPENSEARCH_ENABLED` | `false` | Keep `false` for the lightweight default runtime. Set `true` only when `search` profile is enabled. |
| `COMPOSE_PROFILES` | `` | Empty by default. Use `search`, `crawler`, `monitoring`, or a temporary combination such as `crawler,search` only for targeted validation windows. |
| `PROMETHEUS_PORT` | `9091` | Used only when `monitoring` profile is enabled. Choose a host-local port that does not conflict with other apps. |
| `GRAFANA_PORT` | `3001` | Used only when `monitoring` profile is enabled. Choose a host-local port that does not conflict with other apps. |
| `GRAFANA_ADMIN_PASSWORD` | `change-me-monitoring` | Required when `monitoring` profile is enabled. Use a staging-only password. |
| `POSTGRES_MAX_CONNECTIONS` | `64` | Keeps DB connection budget explicit on the shared host. |
| `DB_POOL_MAX_FRONTEND` | `4` | Lower frontend DB pool for shared-host staging. |
| `DB_POOL_MAX_INDEXER` | `6` | Lower indexer DB pool for shared-host staging. |
| `DB_POOL_MAX_INDEXER_WORKER` | `8` | Job-worker DB pool, sized for the conservative async defaults. |
| `DB_POOL_MAX_INDEXER_MAINTENANCE` | `2` | Maintenance worker only needs a small pool. |
| `DB_POOL_MAX_CRAWLER` | `4` | Used only when `crawler` profile is enabled. |
| `CRAWL_CONCURRENCY` | `2` | Conservative crawler concurrency for temporary crawler test windows. |
| `CRAWL_AUTO_START` | `false` | Required when `crawler` profile is enabled on a shared host. |
| `INDEXER_JOB_WORKERS` | `1` | Conservative async index worker count for staging. |
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

## Initial Validation Checklist
Run these checks right after deployment.

### 1) Service health
- Open `https://<staging-frontend-domain>/health`
- Expect JSON: `{"status":"ok"}`

### 2) Admin login
- Open `https://<staging-frontend-domain>/admin/login`
- Login with staging admin credentials.

### 3) Async index queue behavior
Use any HTTP client from a trusted network path to indexer service (Coolify terminal or internal curl):

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
./scripts/ops/coolify_staging_smoke.sh \
  https://<staging-frontend-domain> \
  http://indexer:8000 \
  <INDEXER_API_KEY> \
  https://example.com
```

### 4) Optional: search validation
Enable `COMPOSE_PROFILES=search` and set `OPENSEARCH_ENABLED=true`, then redeploy.

- Confirm `GET /readyz` reports `opensearch.status = ok`
- Re-run the smoke command above
- Search from frontend UI and confirm indexed documents appear

### 5) Optional: crawl -> index validation
Enable `COMPOSE_PROFILES=crawler,search` only for the test window, then redeploy.

- Open `/admin/crawlers`
- Start crawler manually
- Enqueue a known URL from admin queue UI
- Confirm crawler history shows `queued_for_index`
- Stop the crawler after validation
- Clear `COMPOSE_PROFILES` again when finished

### 6) Optional: monitoring validation
Enable `COMPOSE_PROFILES=monitoring`, then redeploy.

- Confirm inside the server:
  - `curl -s http://127.0.0.1:<PROMETHEUS_PORT>/targets`
  - `curl -s http://127.0.0.1:<GRAFANA_PORT>/api/health`
- Use SSH port-forwarding from your workstation:

```bash
ssh -L 3001:127.0.0.1:3001 -L 9091:127.0.0.1:9091 root@5.223.74.201
```

- Open `http://localhost:3001`
- Login with `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`
- Confirm the provisioned `Web Search Overview` dashboard is visible

## Rollout Safety Notes
- Never reuse production DB or secrets.
- Keep indexer/crawler private; expose only frontend publicly.
- Keep `COMPOSE_PROFILES` empty by default on shared hosts.
- Only enable `crawler` / `search` / `monitoring` profiles for short validation windows.
- Tune `INDEXER_JOB_WORKERS` and `CRAWL_CONCURRENCY` gradually while watching queue growth.

## Rollback Procedure
Use this if staging becomes unhealthy after a deploy.

1. Open Coolify and select the staging application.
2. Redeploy the last known-good commit from deployment history.
3. Clear `COMPOSE_PROFILES` first unless the failing test explicitly needs them.
4. If queue pressure is high, set conservative worker values:
   - `INDEXER_JOB_WORKERS=1`
   - `INDEXER_JOB_CONCURRENCY=1`
   - `CRAWL_CONCURRENCY=2`
5. Trigger redeploy and verify:
   - `GET /health` is `200`
   - `pending_jobs` is no longer increasing indefinitely
6. Keep production unchanged during rollback and continue debugging in staging only.
