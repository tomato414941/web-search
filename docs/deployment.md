# Deployment and search-data changes

## Runtime identity

Production uses Docker Compose behind Caddy. Only the frontend is public;
ingestion, crawl workers, databases, and monitoring are private dependencies.
Host addresses, credentials, volume names, and operator-specific commands stay
outside committed documentation.

Deployment sends a source bundle and records the deployed commit and bundle
location in an operator state file. The server's Git checkout is for inspection;
its HEAD does not identify the running source bundle. Check the deployed state
and running containers when diagnosing version drift.

Routine changes land on `main`. Production deployment is a separate operator
action after CI. Pushing a commit does not deploy it.

## Verification

The repository's `make verify-prd` / `make verify-compose-prd` commands use
`scripts/ops/verify_compose_deploy.sh` and operator environment settings.
Verification should establish:

1. The deployed state identifies the intended commit.
2. Required Compose services are running and healthy.
3. Frontend readiness reports the expected dependencies, including OpenSearch.
4. A known search query returns a non-degraded response and expected content.

Readiness currently gates only on PostgreSQL. The verification script can skip
its public search check when OpenSearch is not reported healthy; inspect that
outcome rather than treating process health as evidence of working search.

## Projection refresh versus schema replacement

`search-projection-rebuild` projects stored PostgreSQL documents and current
link ranks into OpenSearch. It does not re-fetch raw HTML or recalculate ranks.
Recalculation alone also does not refresh existing search documents.

The rebuild CLI upserts eligible documents. Rebuilding an existing index is not
an exact replacement of its contents: documents no longer eligible for projection
can remain there. Use a fresh physical index when an exact replacement or a
mapping change is required.

For a physical-index change:

1. Create/populate a new target with the intended mapping and projection.
2. Verify mapping, counts with exclusions accounted for, representative documents,
   and search behavior against that target.
3. Switch the serving `OPENSEARCH_INDEX_NAME` and verify public search.
4. Keep the previous index available until the change is verified so that the
   operator can switch back if needed.

`ensure_index` does not migrate an existing mapping. Host-specific rebuild,
cutover, and rollback commands belong in the private operator runbook.

## Local profiles

`docs/setup.md` contains the local startup procedure. Compose's `search` profile
starts OpenSearch; `OPENSEARCH_ENABLED` separately controls its use by services.
`crawler`, `monitoring`, and `embedding` enable their optional services.
Embedding backfill does not enable a vector search API.
