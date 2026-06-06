# Operator Priority Crawl Request

## Problem

Operators sometimes need to tell the system that a specific URL should be
crawled soon, but the intended product requirement is not "run the full crawler
pipeline synchronously inside an HTTP request."

The current `POST /crawl-requests` path satisfies the request by immediately
fetching the URL and submitting it to the indexer. That mixes operator intent,
URL registration, frontier leasing, fetching, parsing, and indexer submission in
one synchronous API path.

## Desired Capability

The system should support an operator action equivalent to:

"Make this URL a high-priority crawl target."

That capability should be explicit about whether it only registers a known URL,
adds or updates frontier scheduling state, or forces priority over ordinary
crawler-discovered URLs.

## Impact

Without a clearer model:

- direct crawl APIs can bypass the normal worker execution model
- URL registry ownership becomes harder to reason about
- frontier scheduling and API request handling stay coupled
- retry, timeout, lease, and indexing behavior depend on an operator HTTP call
  rather than the normal crawler runtime

## Direction

Separate the operator request from synchronous crawl execution.

Likely target shape:

- URL registration remains separate from crawl scheduling
- operator priority is represented as frontier scheduling intent
- workers perform fetch/parse/index handoff through the normal crawler pipeline
- if a one-off diagnostic fetch is still needed later, implement it as a
  separate CLI/debug tool rather than as the primary crawl request API

This issue does not require keeping the current `POST /crawl-requests`
implementation.
