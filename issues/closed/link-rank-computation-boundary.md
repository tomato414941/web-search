# Link Rank Computation Boundary

## Status

Closed.

PageRank and domain-rank computation were moved out of the indexer service and
into the `web-model` boundary.

## Former Problem

PageRank and domain-rank computation previously lived in the indexer service
even though they consumed the Web link graph.

That made document indexing responsible for a graph-derived maintenance concern
that is not document ingestion.

## Resolution

- `packages/web-model` owns graph-derived rank calculation code.
- `packages/web-model` owns the rank calculation DB helper.
- `web-search-calc-pagerank` is now a `web-search-web-model` CLI.
- periodic PageRank/domain-rank execution runs from
  `web-model-maintenance-worker`.
- `apps/indexer` no longer contains PageRank/domain-rank calculation code.
- `indexer-maintenance-worker` handles index job cleanup only.

## Remaining Questions

- Are `page_ranks` and `domain_ranks` search-ranking outputs, graph-analysis
  outputs, or both?
- Do we actually need page-level PageRank, or is domain-level authority enough
  for the current product?
- Should rank computation run continuously, on schedule, or only manually until
  its value is proven?

Full-graph read cost remains a separate scale concern, not an indexer ownership
boundary concern.

## Related

- `issues/web-model-boundary.md`
- `issues/indexer-manual-ranking-recalculation-api.md`
- `issues/links-physical-schema-drift.md`
