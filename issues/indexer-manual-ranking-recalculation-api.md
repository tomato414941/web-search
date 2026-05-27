# Indexer Manual Ranking Recalculation API

## Problem

The indexer exposes synchronous HTTP endpoints for manually recalculating
ranking signals:

- `POST /api/v1/indexer/pagerank`
- `POST /api/v1/indexer/origin-scores`

These endpoints may be useful as operator controls, but it is not yet clear
whether synchronous HTTP is the right execution boundary for potentially heavy
ranking recalculation work.

## Evidence

`pagerank` is not only an HTTP endpoint. The same work is also available through
the `web-search-calc-pagerank` CLI and through indexer worker maintenance loops.

`origin-scores` currently has an HTTP trigger and participates in search signal
calculation, but there is no clear operator workflow in the admin UI or runbook
that explains when it should be manually triggered through the API.

## Impact

Keeping these endpoints without a clear operating model can make the indexer API
look like a general admin surface rather than a focused ingestion API.

If the recalculation work is heavy, synchronous HTTP execution may also be a poor
fit because request timeouts, retries, and duplicate operator triggers can be
harder to reason about than CLI or scheduled worker execution.

## Direction

Do not remove these endpoints immediately.

Revisit them when ranking recalculation operations are reviewed. Decide whether
manual recalculation should be:

- kept as authenticated HTTP endpoints
- moved to CLI-only operation
- handled only by scheduled worker maintenance
- exposed through a future admin operation with explicit status and safeguards
