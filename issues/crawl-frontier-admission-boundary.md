# Crawl Frontier Admission Boundary

## Problem

The project needs a clear boundary for deciding when a known URL becomes a crawl
target.

Frontier admission should not be hidden behind a generic URL registration API.

## Evidence

The previous crawler `POST /urls` path admitted URLs into `frontier_entries` as
part of a request named like URL registration. Internally this called
`discover_and_admit_urls(..., discovered_via="manual")`.

## Impact

- It is hard to tell whether an API is registering knowledge or scheduling work.
- Admission policy changes can accidentally affect URL registry behavior.
- URL registry redesign is harder while registration and frontier admission are
  a single operation.

## Direction

Define frontier admission as an explicit scheduling operation.

Likely target shape:

- known URL registration and frontier admission are separate concepts
- admission intent is explicit, such as crawler discovery, seed, feed
  autodiscovery, operator request, or recovery
- `frontier_entries` remains the source of truth for crawl target/schedule state
