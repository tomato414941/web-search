# Ranking Recalculation Execution Boundary

## Problem

The indexer has exposed synchronous HTTP endpoints for manually recalculating
ranking signals:

- `POST /api/v1/indexer/pagerank` (removed; PageRank uses maintenance worker
  and CLI entrances)
- `POST /api/v1/indexer/origin-scores` (removed; the signal was too weakly
  supported to expose or use as a ranking/document signal)

These endpoints may be useful as operator controls, but it is not yet clear
whether synchronous HTTP is the right execution boundary for potentially heavy
ranking recalculation work.

The desired capability is not an HTTP endpoint itself. The desired capability is
that ranking signals are refreshed reliably, remain operationally visible, and
can be rerun deliberately when needed.

## Evidence

`pagerank` is available through the `web-search-calc-pagerank` CLI and through
indexer worker maintenance loops.

`origin-scores` used an inlink/outlink/word-count heuristic with a stronger
name than the implementation justified. It has been removed from the indexer
HTTP API, OpenSearch documents, public search responses, and MCP formatting.

The project already runs an `indexer-maintenance-worker` service. It handles
periodic PageRank, domain-rank, and job-cleanup work.

The historic `information_origins` table still exists in the baseline migration,
but it is no longer part of the runtime ranking or response surface.

## Impact

Keeping these endpoints without a clear operating model can make the indexer API
look like a general admin surface rather than a focused ingestion API.

If the recalculation work is heavy, synchronous HTTP execution may also be a poor
fit because request timeouts, retries, and duplicate operator triggers can be
harder to reason about than CLI or scheduled worker execution.

The deeper risk is that ranking maintenance becomes split across multiple
entrances without a single operational source of truth for execution state,
failure, and rerun behavior.

Weakly grounded signals also create trust risk when they are named or displayed
as stronger judgments than the implementation can support.

## Direction

Do not treat the HTTP endpoints as the desired design by default.

Revisit them when ranking recalculation operations are reviewed. Decide whether
ranking recalculation should be:

- handled by scheduled maintenance worker execution
- exposed through CLI-only manual execution
- represented as explicit operation jobs with status, history, and duplicate-run
  safeguards
- kept as authenticated HTTP endpoints only if there is a concrete caller and a
  clear operating model

The likely near-term direction is:

- scheduled refresh: `indexer-maintenance-worker`
- manual rerun: CLI
- future richer control: operation/job system
- indexer ingestion API: no ranking-maintenance endpoints

## Open Questions

- Is CLI-only manual execution sufficient for current operations?
- If an operation/job system is introduced, where should its state live?
- What metrics or logs are required to make ranking maintenance failures visible?
- Should the unused `information_origins` table be removed from the schema
  baseline when database cleanup is reviewed?
