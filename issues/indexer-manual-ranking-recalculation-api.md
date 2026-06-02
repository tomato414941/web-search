# Ranking Recalculation Execution Boundary

## Problem

The indexer exposes synchronous HTTP endpoints for manually recalculating
ranking signals:

- `POST /api/v1/indexer/pagerank`
- `POST /api/v1/indexer/origin-scores`

These endpoints may be useful as operator controls, but it is not yet clear
whether synchronous HTTP is the right execution boundary for potentially heavy
ranking recalculation work.

The desired capability is not an HTTP endpoint itself. The desired capability is
that ranking signals are refreshed reliably, remain operationally visible, and
can be rerun deliberately when needed.

## Evidence

`pagerank` is not only an HTTP endpoint. The same work is also available through
the `web-search-calc-pagerank` CLI and through indexer worker maintenance loops.

`origin-scores` currently has an HTTP trigger and participates in search signal
calculation, but there is no clear operator workflow in the admin UI or runbook
that explains when it should be manually triggered through the API.

The project already runs an `indexer-maintenance-worker` service. It handles
periodic PageRank, domain-rank, and job-cleanup work. This means PageRank has at
least two execution entrances today: scheduled maintenance and synchronous HTTP.

Origin-score recalculation is not currently aligned with that maintenance-worker
execution model.

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

- scheduled refresh: `indexer-maintenance-worker`
- manual rerun: CLI
- future richer control: operation/job system
- indexer ingestion API: no ranking-maintenance endpoints

## Open Questions

- Should origin-score recalculation move into the maintenance worker?
- Is CLI-only manual execution sufficient for current operations?
- If an operation/job system is introduced, where should its state live?
- What metrics or logs are required to make ranking maintenance failures visible?
