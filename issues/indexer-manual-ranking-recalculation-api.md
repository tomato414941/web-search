# Ranking Recalculation Execution Boundary

## Problem

The indexer has exposed synchronous HTTP endpoints for manually recalculating
ranking signals.

The PageRank HTTP endpoint has been removed; PageRank now uses Web model
maintenance worker and CLI entrances.

These endpoints may be useful as operator controls, but it is not yet clear
whether synchronous HTTP is the right execution boundary for potentially heavy
ranking recalculation work.

The desired capability is not an HTTP endpoint itself. The desired capability is
that ranking signals are refreshed reliably, remain operationally visible, and
can be rerun deliberately when needed.

## Evidence

`pagerank` is available through the `web-search-calc-pagerank` CLI and through
Web model worker maintenance loops.

The project runs a `web-model-maintenance-worker` service for periodic PageRank
and domain-rank work.

## Impact

Keeping these endpoints without a clear operating model can make the indexer API
look like a general admin surface rather than a focused ingestion API.

If the recalculation work is heavy, synchronous HTTP execution may also be a poor
fit because request timeouts, retries, and duplicate operator triggers can be
harder to reason about than CLI or scheduled worker execution.

The deeper risk is that ranking maintenance becomes split across multiple
entrances without a single operational source of truth for execution state,
failure, and rerun behavior.

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

- scheduled refresh: `web-model-maintenance-worker`
- manual rerun: CLI
- future richer control: operation/job system
- indexer ingestion API: no ranking-maintenance endpoints

## Open Questions

- Is CLI-only manual execution sufficient for current operations?
- If an operation/job system is introduced, where should its state live?
- What metrics or logs are required to make ranking maintenance failures visible?
