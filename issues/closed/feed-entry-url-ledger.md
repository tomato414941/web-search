# Feed Entry URL Ledger

## Status

Closed. Feed entry URLs are recorded in the `urls` ledger without being admitted
to `frontier_entries`.

## Problem

Feed entries can be indexed from a fetched RSS/Atom feed, but it is not clear
that each entry URL is also recorded as a discovered URL in the `urls` ledger.

If feed entry URLs bypass the normal URL ledger, the search index may know about
documents that the crawler URL ledger cannot explain.

## Evidence

The feed processing path parses feed entries and submits them to the indexer.
The normal HTML path admits discovered outlinks through
`url_store.discover_and_admit_urls()`.

Feed entry URLs should be checked for the same kind of ledger/admission behavior
expected from ordinary discovered URLs.

## Impact

If feed entry URLs are not recorded in `urls`:

- crawl history may be incomplete
- source coverage debugging becomes harder
- recrawl behavior for feed-discovered articles may be unclear
- index contents and crawler ledger can drift conceptually

## Direction

Confirm whether feed entry URLs are recorded in `urls`. If they are not, route
them through the normal URL discovery path unless there is a concrete reason to
keep feed-only indexing separate.

Keep the first fix narrow: make feed-discovered article URLs visible in the same
ledger model as other discovered URLs.

## Resolution

URL discovery and frontier admission are now separate store operations.

Feed entry URLs use `record_discovered_urls(...)`, which records them in `urls`
without scheduling them in `frontier_entries`.
