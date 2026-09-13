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
4. A known search query returns HTTP 200, `mode: "hybrid"`, and expected content.

Frontend readiness checks the configured hybrid index and pipeline. The public
search check is mandatory and also exercises query embedding generation.

## Projection refresh versus schema replacement

`search-projection-rebuild` projects stored PostgreSQL documents into the hybrid
OpenSearch schema, generating embeddings. It does not re-fetch raw HTML.

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

## Hybrid cutover

The default index is `documents-hybrid-v2`, using 1,024-dimensional Perplexity
embeddings through OpenRouter. Existing lexical indexes and the previous
1,536-dimensional OpenAI hybrid index are rejected rather than upgraded in place.
Provision OpenSearch 2.19.6 and `OPENROUTER_API_KEY`, rebuild into a fresh index,
then deploy the matching application and MCP client together. Old `mode` query
parameters are rejected. There is no old-schema
reader, dual-write path, or automatic lexical fallback. A rollback requires
restoring the corresponding application release and its index together.

Full-corpus embedding generation is a separate, potentially costly operation;
check document count, provider quota, storage capacity, and estimated token
volume before running it. The Compose memory defaults are development settings,
not a capacity guarantee for a full Web corpus.

## Local profiles

OpenSearch is mandatory. `crawler` and `monitoring` remain optional profiles.
The `crawler` profile also starts the R2 link archive worker.
The separate embedding-backfill service and periodic link-rank worker have been
removed from the serving stack. `docs/setup.md` contains the local procedure.

## Link archive cutover

Before migration `021`, stop and drain all old crawler/link writers and stop any
old rank worker. The migration renames `links` to the write-protected
`legacy_links` without copying or deleting it. New observations use the outbox.
Set the `R2_*` values from `.env.example` in the production environment file,
then deploy the crawler and archive worker together.

Run `web-search-link-archive export-legacy` in the archive container once. It
resumes from its verified checkpoint, registers old discoveries in the URL ledger,
and assigns revision zero with unknown observation timestamps. Run `compact` and
inspect `status` and representative `get URL` results before separately retiring
the frozen table. Export does not delete PostgreSQL data. Upload, retry, daily
snapshots, and collection run automatically afterward.
