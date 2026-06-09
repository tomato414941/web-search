# Web Knowledge Boundary

## Problem

The project lacks an explicit code and ownership boundary for structural facts
observed from the Web.

`urls` and `links` belong to the same conceptual area:

- `urls` are known URL nodes
- `links` are observed URL-to-URL edges

Today those responsibilities are split. URL registration has been moved toward a
URL ledger concept, but link graph writes still happen through the indexer and
document repository path. That makes observed Web structure look like a side
effect of document indexing.

## Evidence

Current behavior:

- the crawler fetches and parses pages
- the crawler observes outlinks
- the crawler records discovered URLs for URL registration and crawl admission
- the crawler sends outlinks to the indexer
- the indexer writes `links`

This means `links` currently represents links from pages that reached indexing,
not necessarily the full set of links observed during crawling/parsing.

The current top-level package boundaries also hide the issue:

- `packages/postgres` contains repositories for documents, index jobs, ranking,
  and URL registration
- `urls` and `links` are not owned by one explicit Web-structure boundary
- `index_jobs.outlinks` carries Web graph data through the document indexing
  queue

## Impact

- `urls` and `links` can drift into different meanings even though they are node
  and edge data for the same Web graph.
- The indexer owns a Web observation concern that should not belong to document
  indexing.
- Link graph changes require touching crawler, indexer, document repositories,
  index jobs, and PostgreSQL schema details.
- The intended invariants for `links` are unclear, including whether `src`
  means crawled-and-parsed URL or indexed document URL.

## Direction

Define a `web-knowledge` boundary for structural Web facts.

Initial ownership:

- known URLs
- observed links between URLs

Likely future ownership:

- feed URL observations
- sitemap URL observations
- canonical URL relations
- observed domain-level facts that are not crawler runtime state

Explicit non-ownership:

- crawler runtime state such as fetch scheduling, leases, retries, robots, and
  crawl delay
- document indexing state such as `documents`, `index_jobs`, and OpenSearch
  writes
- ranking outputs such as `page_ranks` and `domain_ranks`
- search telemetry such as search requests, impressions, and clicks

Target shape:

- crawler observes the Web and writes URL/link observations into web knowledge
- indexer writes searchable documents and does not write the link graph
- `urls` and `links` are managed through the same conceptual boundary
- `links` represents observed URL references, not indexing side effects

## Open Questions

- Should the package name be `web-knowledge`, `web-memory`, or another name?
- Should `src` be defined as any successfully parsed URL, or only URLs accepted
  as crawl targets?
- Should `dst` include every normalized discovered URL, including URLs not yet
  crawled or indexed?
- Should feed entry relationships be stored in the same `links` table or as a
  typed relation later?

## Notes

Do not combine this ownership move with physical `links` schema repair.

The production `links` table is large. Deduplication, `UNIQUE(src, dst)`, and
`dst` indexing should be planned separately after the ownership boundary is
clear.
