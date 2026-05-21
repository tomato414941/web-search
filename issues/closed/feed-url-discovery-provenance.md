# Feed URL Discovery Provenance

## Problem

Discovered feed URLs should go through the same `urls` and `frontier_entries`
flow as ordinary discovered URLs, but their discovery route should remain
understandable.

If feed URLs are admitted as generic outlinks, operators and future ranking or
crawl-policy code cannot tell whether a URL came from a normal page link or a
feed autodiscovery signal.

## Evidence

URL admission already tracks `discovered_via` for routes such as outlink, seed,
and manual admission. RSS/Atom autodiscovery is conceptually another discovery
route, not a separate storage model.

## Impact

Without clear provenance, feed discovery may become hard to debug:

- discovered feeds may look like ordinary outlinks
- crawl policy cannot easily treat feed URLs differently if needed
- source coverage investigations may lose the reason a feed entered the system

## Direction

Use the existing URL ledger and frontier admission flow for discovered feed
URLs, while preserving a distinct discovery route such as `feed_autodiscovery`
if implementation work adds RSS/Atom alternate-link extraction.

Do not introduce a separate manual or RSS-only ingestion path for this unless
the existing URL discovery model proves insufficient.
