# URL Registry Ownership

## Problem

`urls` is currently implemented inside the crawler storage layer, but the table
represents more than crawler-owned state.

Conceptually, `urls` is the set of URLs known to this project. The crawler is one
way to discover URLs, but it is not the only possible source. Manual operator
input, seeds, feeds, sitemaps, and future submission paths can also introduce
known URLs.

Treating `urls` as crawler-owned state makes the crawler boundary look broader
than it should be.

## Evidence

Current URL sources already include multiple intents:

- seed registration
- manual operator admission
- crawler-discovered outlinks
- feed autodiscovery
- feed entry recording

The current implementation stores these through crawler-side `CrawlerRuntimeStore` methods,
often coupled to frontier admission.

Related issues already cover narrower parts of the problem:

- `urls-ledger-responsibility.md` covers which columns belong in `urls`
- `frontier-entries-responsibility.md` covers what `frontier_entries` represents
- `frontier-admission-routes-responsibility.md` covers admission intent routing

This issue covers the higher-level ownership question.

## Impact

- `urls` can be mistaken for crawler worker state rather than project-wide URL
  registry state.
- Previous API routes such as `POST /urls` appeared to belong to the crawler
  service even though they represented URL registry or admission concepts.
- URL registration and frontier admission stay too tightly coupled.
- Future URL sources may be added through crawler-specific paths because there is
  no explicit URL registry boundary.

## Direction

Define a URL registry boundary before further schema or API cleanup.

Likely target shape:

- `urls` represents known URL identity for the project
- URL discovery sources write through a URL registry/admission layer
- crawler workers consume crawl targets; they are not the conceptual owner of
  the known URL set
- frontier state remains separate from URL registry state
- direct crawl requests are reviewed separately from URL registration

Do not rename tables or move services until the intended boundary is clear.
