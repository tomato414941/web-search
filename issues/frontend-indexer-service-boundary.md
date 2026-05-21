# Frontend Indexer Service Boundary

## Problem

The project does not yet have a clear way to judge whether keeping `frontend`
and `indexer` as separate services continues to be worth its operational and
development cost.

Today, `frontend` owns the public read/admin surface while `indexer` owns the
private write/indexing surface. That split has real value, but it also adds an
internal API boundary, separate service configuration, deployment coordination,
and observability overhead.

## Evidence

Current service responsibilities:

- `apps/frontend`: public search API, content API, admin UI, and MCP-facing
  stats surface.
- `apps/indexer`: page ingestion, indexing jobs, PostgreSQL writes, and
  OpenSearch sync.

The boundary is not currently the main observed production issue. Current
production issues are more directly tied to crawler stats aggregation cost and
Tier 1 search quality.

## Impact

Without explicit signals, the project may keep paying service-to-service
complexity without knowing whether the separation is still earning its cost.

The reverse risk is also real: collapsing the services too early could remove a
useful separation between public read paths and private write/indexing paths.

## Direction

Treat this as an observation issue, not as a decision to merge services.
Reevaluate the boundary when there is concrete evidence that it is causing
recurring operational or development friction.

Useful signals:

- frequent coordinated changes across `frontend` and `indexer`
- internal APIs becoming thin pass-through layers
- service-to-service auth/config/deploy becoming a recurring failure source
- little practical benefit from keeping the write path private
- local development or production debugging dominated by the split

Until then, keep the current boundary and focus on observed production issues.
