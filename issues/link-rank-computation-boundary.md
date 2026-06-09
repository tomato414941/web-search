# Link Rank Computation Boundary

## Problem

PageRank and domain-rank computation currently live in the indexer service even
though they consume the Web link graph.

`links` is now owned as observed Web structure by the `web-knowledge` boundary.
However, the rank computation that reads that graph still sits under
`apps/indexer`, and it reads the graph through PostgreSQL repositories that load
large portions of `links` into Python memory.

This makes document indexing responsible for a graph-derived maintenance
concern that is not document ingestion.

## Evidence

Current behavior:

- crawler observes links and writes them through `web-knowledge`
- `apps/indexer/src/web_search_indexer/services/pagerank.py` computes page and
  domain ranks
- `RankingRepository.fetch_links()` runs `SELECT src, dst FROM links`
- PageRank and domain-rank loops run from `indexer-maintenance-worker`
- OpenSearch indexing reads the computed `page_ranks` and `domain_ranks`

The heaviest path is not the rank lookup during indexing. It is the periodic
rank computation path that reads the full `links` graph.

## Impact

- The indexer remains coupled to Web graph ownership even after link writes were
  moved out of indexing.
- Large `links` tables make full graph reads expensive in memory, query time,
  and operational risk.
- Rank maintenance, document ingestion, and graph ownership are blurred into the
  same service boundary.
- It is hard to decide whether rank computation should be optimized, disabled,
  scheduled differently, or moved because the current ownership is unclear.

## Direction

Treat link-rank computation as graph-derived maintenance, not document indexing.

Decide the intended owner and execution model before optimizing the SQL:

- `web-knowledge` owns the observed URL graph
- rank outputs such as `page_ranks` and `domain_ranks` are derived data
- document indexing may consume rank outputs, but should not own graph
  computation by default
- heavy graph computation should not require loading all `links` rows into
  indexer memory as the assumed design

Possible target shapes:

- move graph-derived rank computation into a dedicated maintenance boundary
- keep only rank-output reads in the indexer
- compute domain-level ranks from pre-aggregated graph facts instead of raw
  links when scale requires it
- make manual recalculation an explicit operation or CLI task, not an indexer API
  concern

## Open Questions

- Should this live under `web-knowledge`, a separate `ranking-maintenance`
  package, or another boundary?
- Are `page_ranks` and `domain_ranks` search-ranking outputs, graph-analysis
  outputs, or both?
- Do we actually need page-level PageRank, or is domain-level authority enough
  for the current product?
- What size of `links` table makes full graph reads unacceptable?
- Should rank computation run continuously, on schedule, or only manually until
  its value is proven?

## Related

- `issues/web-knowledge-boundary.md`
- `issues/indexer-manual-ranking-recalculation-api.md`
