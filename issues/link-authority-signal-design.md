# Link Authority Signal Design

## Problem

The project treats PageRank as an important search-engine signal, but the
current authority path is not yet a coherent operation.

The issue is not that PageRank is unnecessary. The issue is that link-derived
authority is currently split across graph calculation, stored rank tables,
OpenSearch document projections, frontend reranking, and search evaluation.

As a result, it is hard to tell whether PageRank is actually improving search
quality or merely existing as a weak signal.

## Evidence

Current behavior:

- `packages/web-model` calculates page-level and domain-level PageRank from
  `links`
- results are stored in `page_ranks` and `domain_ranks`
- indexer reads those rank tables when building OpenSearch documents
- OpenSearch stores `page_rank` and `domain_rank` as document fields
- frontend reranking uses those fields as late tie-breaker signals for some
  query classes

This means recalculating PageRank does not by itself update the search-time
projection. Existing OpenSearch documents keep their old `page_rank` and
`domain_rank` values until they are reindexed or backfilled.

## Impact

- PageRank can be stale in search results even after rank recalculation
  succeeds.
- The value of page-level PageRank is hard to judge because the effect is weak,
  indirect, and not tied to an evaluation loop.
- The system has no single authority-refresh operation that covers calculation,
  projection update, and quality verification.
- It is unclear whether `page_ranks` and `domain_ranks` are Web model
  attributes, search-ranking signals, or temporary OpenSearch projection inputs.

## Direction

Design link-derived authority as an explicit search quality signal.

The intended operation should be:

- compute authority from the Web model graph
- store the authoritative values in the Web model boundary
- update the search projection that consumes those values
- verify that ranking behavior does not regress

Do not frame the decision as simply deleting or preserving PageRank. Decide what
authority signal the search engine needs, then align the tables, names,
projection path, ranking policy, and evaluation path with that decision.

Likely target shape:

- `domain_rank` or `domain_authority` remains as the broad source-authority
  signal
- page-level authority remains only if it has a clear search use case and
  projection refresh path
- rank recalculation and OpenSearch projection refresh become one operational
  unit
- frontend reranking treats authority as an explicit weak prior, not as an
  opaque aggregate score

## Open Questions

- Should the public/internal field be named `page_rank` or `page_authority`?
- Should `domain_rank` be renamed to `domain_authority`?
- Should page-level authority be computed over indexed documents only, or over
  the broader known URL/link graph?
- Which query classes should use link-derived authority?
- How should authority refresh update existing OpenSearch documents?
- What search evaluation cases should prove that authority is helping rather
  than hiding retrieval failures?

## Related

- `issues/web-model-boundary.md`
- `issues/links-physical-schema-drift.md`
- `issues/closed/link-rank-computation-boundary.md`
