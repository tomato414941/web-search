# Persistent Seed URL Management

## Problem

The project may not need to persistently manage "seed URLs" as a special URL
category.

The original need is simpler: operators need a way to give the system starting
URLs. That does not necessarily require a durable `is_seed` flag, seed-specific
recrawl policy, seed-specific priority behavior, or a seed management HTTP API.

## Evidence

Prior seed handling bundled several concerns:

- seed URL registration
- `urls.is_seed`
- frontier admission
- seed-based priority boosts
- seed-specific recrawl intervals
- `/seeds` list/add/delete API
- CLI submission through the seed API

This overlaps with the broader URL registry, frontier admission, operator
intent, and crawl priority questions already tracked separately.

## Impact

- `urls` carries a durable category that may only describe an initial import
  event.
- Seed management makes URL registry redesign harder.
- Seed-specific priority and recrawl behavior can hide scheduling policy inside
  URL provenance.
- An API for listing and deleting seeds may create management surface without a
  clear operator decision.

## Direction

Do not treat seed URLs as an active management surface or durable URL category.

Current target shape:

- initial URL input can be handled by an operator import or URL registration
  workflow
- persistent `is_seed` is removed
- seed-specific priority and recrawl policy are removed
- `/seeds` HTTP management should not be restored without a clear operator use
  case
