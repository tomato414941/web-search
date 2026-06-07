# Canonical Source Concept Responsibility

## Problem

The project uses `canonical_source` as a shared concept across search
configuration, crawler scheduling, and ranking policy, but the concept is not
precise enough to carry all of those responsibilities.

The name suggests an authoritative or primary source, while the implementation
is a manually maintained URL/domain/path policy hint.

## Evidence

Current crawler behavior stores `canonical_source` in `crawl_schedule` and uses
it to shorten successful recrawl intervals.

Current frontend ranking behavior does not read `crawl_schedule.canonical_source`.
It independently reads `config/canonical_sources.json` and computes URL/source
fit at ranking time.

The same configuration therefore acts as:

- a search evaluation/source expectation list
- a ranking signal registry
- a crawler URL classification input
- a crawler recrawl-frequency input

## Impact

- The crawler depends on a hand-maintained source registry instead of observed
  crawl value, freshness, or demand signals.
- `crawl_schedule` stores a policy classification snapshot that can become stale
  when `canonical_sources.json` changes.
- The term `canonical_source` makes a weak heuristic look like a stronger
  truth than it is.
- Search ranking, search evaluation, and crawl scheduling are harder to reason
  about because they share one broad label.

## Direction

Separate the responsibilities currently hidden behind `canonical_source`.

Likely target shape:

- crawler scheduling does not depend on a `canonical_source` label
- recrawl priority is based on crawl value, freshness, observed change, demand,
  or explicit scheduling intent
- ranking may still use a source-fit policy, but it should be named and scoped
  as a ranking signal rather than a global canonical truth
- search evaluation should describe expected results for queries, not define a
  global source authority concept
