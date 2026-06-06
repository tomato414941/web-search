# Known URL Registration Boundary

## Problem

The project needs a clear boundary for recording that a URL is known to the
system.

This is different from deciding whether the URL should be crawled now, crawled
later, or not crawled at all.

## Evidence

The previous crawler `POST /urls` path mixed URL registration with frontier
admission and operator priority. That made it look like adding a URL to the
project's known URL set was the same operation as scheduling a crawl.

## Impact

- `urls` can be mistaken for a crawler queue.
- URL registry ownership becomes harder to separate from crawler runtime state.
- Future URL sources may be forced through frontier-specific APIs.

## Direction

Define known URL registration as its own concept.

Likely target shape:

- registering a known URL records identity and provenance
- registration does not imply immediate crawl scheduling
- crawler, feeds, seeds, operators, and future submission paths can all be URL
  sources
- frontier admission is a separate decision
