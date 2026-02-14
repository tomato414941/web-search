# Coolify Staging Setup

This guide defines a staging environment that mirrors production deployment flow on Coolify.

## Goal
- Use the same deployment path as production (Coolify + Docker Compose).
- Keep staging resources isolated from production.
- Validate async indexing flow (`202 + job_id`) before production release.

## Deployment Topology
- `frontend`: public (staging domain)
- `indexer`: private (internal network only)
- `crawler`: private (internal network only)
- `postgres`: private (internal network only)

## Coolify App Configuration
1. Create a separate Coolify Project for staging (for example `web-search-staging`).
2. Create a new Application from this repository.
3. Select `Docker Compose` deployment.
4. Set Compose file path to `docker-compose.coolify.yml`.
5. Set branch to staging target branch (for example `main` or `staging`).
6. Expose only `frontend` service on a public domain.

## Required Environment Variables
Set these in Coolify application environment variables.

| Variable | Example | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | `production` | Keep production-like behavior in staging. |
| `POSTGRES_PASSWORD` | `change-me-strong` | Use a unique strong password. |
| `ADMIN_USERNAME` | `admin` | Staging admin login user. |
| `ADMIN_PASSWORD` | `change-me` | Staging-only credential. |
| `ADMIN_SESSION_SECRET` | `change-me-long-random` | 32+ chars random string. |
| `ALLOWED_HOSTS` | `stg-search.example.com` | Include staging domain only. |
| `ANALYTICS_SALT` | `change-me-random` | Random salt for analytics hashing. |
| `INDEXER_API_KEY` | `change-me-random` | Shared secret between crawler/frontend and indexer. |
| `OPENAI_API_KEY` | `` | Optional. Leave empty to disable embeddings. |
| `CRAWL_CONCURRENCY` | `10` | Initial crawler concurrency. |
| `INDEXER_JOB_WORKERS` | `4` | Async index worker count. |
| `INDEXER_JOB_BATCH_SIZE` | `20` | Max claimed jobs per poll. |
| `INDEXER_JOB_LEASE_SEC` | `120` | Job lease duration. |
| `INDEXER_JOB_MAX_RETRIES` | `5` | Retry cap before permanent failure. |
| `INDEXER_JOB_POLL_INTERVAL_MS` | `200` | Worker poll interval. |
| `INDEXER_JOB_RETRY_BASE_SEC` | `5` | Exponential retry base. |
| `INDEXER_JOB_RETRY_MAX_SEC` | `1800` | Exponential retry ceiling. |

## Initial Validation Checklist
Run these checks right after deployment.

### 1) Service health
- Open `https://<staging-frontend-domain>/health`
- Expect JSON: `{"status":"ok"}`

### 2) Admin login and crawler startup
- Open `https://<staging-frontend-domain>/admin/login`
- Login with staging admin credentials.
- Start crawler from `/admin/crawlers`.

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
./scripts/coolify_staging_smoke.sh \
  https://<staging-frontend-domain> \
  http://indexer:8000 \
  <INDEXER_API_KEY> \
  https://example.com
```

### 4) End-to-end crawl -> search
- Enqueue a known URL from admin queue UI.
- Confirm crawler history shows `queued_for_index`.
- Search from frontend UI and confirm document appears.

## Rollout Safety Notes
- Never reuse production DB or secrets.
- Keep indexer/crawler private; expose only frontend publicly.
- Tune `INDEXER_JOB_WORKERS` and `CRAWL_CONCURRENCY` gradually while watching queue growth.

## Rollback Procedure
Use this if staging becomes unhealthy after a deploy.

1. Open Coolify and select the staging application.
2. Redeploy the last known-good commit from deployment history.
3. If queue pressure is high, set conservative worker values:
   - `INDEXER_JOB_WORKERS=1`
   - `CRAWL_CONCURRENCY=2`
4. Trigger redeploy and verify:
   - `GET /health` is `200`
   - `pending_jobs` is no longer increasing indefinitely
5. Keep production unchanged during rollback and continue debugging in staging only.
