# Web Model Boundary

## Problem

The project has started to separate the internal model of the known Web from
crawler runtime and document indexing, but the boundary is not complete yet.

`urls`, `links`, and graph-derived attributes belong to the same broad
conceptual area:

- `urls` are known URL nodes
- `links` are observed URL-to-URL edges
- rank-like values are attributes derived from the URL/link graph

The current package name and write path are moving in the right direction, but
graph-derived maintenance still sits in the indexer boundary.

## Evidence

Current behavior:

- the crawler fetches and parses pages
- the crawler observes outlinks
- the crawler records discovered URLs for URL registration and crawl admission
- the crawler writes observed links through the Web model repository
- the indexer no longer writes `links`
- PageRank and domain-rank computation still live in the indexer service

The current top-level package boundaries also hide the issue:

- `packages/postgres` still contains graph-derived ranking repository helpers
- `apps/indexer` still contains PageRank/domain-rank calculation code
- `packages/web-model` owns URL and link writes, but not all Web-model-derived
  maintenance

## Impact

- Web model ownership remains partially split across package boundaries.
- The indexer still owns a graph-derived maintenance concern that should not
  belong to document indexing.
- Graph-derived rank changes still require touching indexer service code and
  PostgreSQL ranking repositories.
- The intended invariants for `links` are unclear, including whether `src`
  means crawled-and-parsed URL or indexed document URL.

## Direction

Use `web-model` as the boundary for the search engine's internal representation
of the known Web.

Ownership:

- known URLs
- observed links between URLs
- feed URL observations
- sitemap URL observations
- canonical URL relations
- observed domain-level facts that are not crawler runtime state
- graph-derived attributes if they are part of the Web model used by search or
  crawl policy

Explicit non-ownership:

- crawler runtime state such as fetch scheduling, leases, retries, robots, and
  crawl delay
- document indexing state such as `documents`, `index_jobs`, and OpenSearch
  writes
- search telemetry such as search requests, impressions, and clicks

Target shape:

- crawler observes the Web and writes URL/link observations into web model
- indexer writes searchable documents and does not write the link graph
- `urls` and `links` are managed through the same conceptual boundary
- `links` represents observed URL references, not indexing side effects
- graph-derived maintenance is no longer implemented as indexer service logic

## Open Questions

- Should `src` be defined as any successfully parsed URL, or only URLs accepted
  as crawl targets?
- Should `dst` include every normalized discovered URL, including URLs not yet
  crawled or indexed?
- Should feed entry relationships be stored in the same `links` table or as a
  typed relation later?
- Should `page_ranks` and `domain_ranks` live in the Web model boundary, or
  should only their input graph live there?

## Notes

Do not combine this ownership move with physical `links` schema repair.

The production `links` table is large. Deduplication, `UNIQUE(src, dst)`, and
`dst` indexing should be planned separately after the ownership boundary is
clear.
