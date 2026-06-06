# Frontier Admission Routes Responsibility

## Problem

`frontier_entries` admission is implemented through a small number of code
paths, but the product-level reasons for admission are not clearly separated.

Most new frontier rows flow through `discover_and_admit_urls()` or
`discover_and_admit_url()`, which ultimately call `_upsert_frontier_batch()`.
That shared path is good mechanically, but it currently mixes distinct
admission intents such as ordinary crawler discovery, operator priority
admission, and CLI requeue recovery.

This makes it harder to reason about what should happen when admission rules
change.

## Evidence

Observed frontier admission routes:

- HTML outlinks via `admit_discovered_urls(...)`
- feed autodiscovery URLs via `admit_discovered_urls(..., discovery_depth=0)`
- robots-blocked recovery CLI when a URL has no existing frontier entry

Observed non-admission route:

- feed entry URLs are recorded with `record_discovered_urls(...)` and are not
  admitted to the frontier

## Impact

- It is not obvious which routes should respect recent-crawl suppression and
  which should force admission.
- Recent-crawl suppression now uses frontier runtime state, but admission intent
  is still not clearly represented at the product level.
- Manual/operator intent and crawler-discovered intent currently share much of
  the same path, so policy differences are implicit.
- Future feed-specific changes may accidentally admit feed entry URLs if the
  distinction between discovery ledger writes and frontier admission is not kept
  explicit.

## Direction

Define admission intent explicitly before changing suppression rules.

Likely target shape:

- keep one low-level frontier upsert implementation
- make higher-level admission intents explicit, for example normal admission,
  operator priority admission, and recovery requeue
- document which intents can bypass recent-crawl suppression
- keep ledger-only URL recording separate from frontier admission
