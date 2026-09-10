# Link Authority Refresh and Value

## Current behavior

The Web model worker computes page/domain ranks and stores them in PostgreSQL.
The indexer copies those values into OpenSearch during indexing or projection
rebuild. Search uses them as late tie-breakers for selected query classes.

Recalculation does not update existing search documents. A successful rank job
therefore does not establish that current search results use the new ranks.

`RankingRepository.fetch_links()` materializes the full edge list in memory.
The historical schema-repair report recorded a graph too large for that approach;
current capacity must be measured rather than assumed from that old count.

## Decisions and verification needed

- Establish a bounded way to compute the required signal at the actual graph size.
- Define how a completed calculation is projected and how its freshness is observed.
- Compare search outcomes with and without page/domain rank before treating either
  signal as necessary. Their presence in the response is not evidence of value.
- Decide whether calculation should cover all observed URLs or only indexed pages.

The issue may be resolved by improving the refresh path or by removing a signal
that does not justify its cost. No rename, operation UI, or additional ranking
feature is required merely to close this issue.

Historical evidence: `issues/closed/links-physical-schema-drift.md`.
