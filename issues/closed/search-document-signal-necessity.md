# Search Document Signal Necessity

## Status

Closed.

## Problem

The project stored and exposed document-level search signals such as
`temporal_anchor`, `published_at_present`, and `factual_density`, but their
necessity was not clear enough to justify the runtime and API surface.

This issue is about the signals themselves, not the older field-specific
backfill commands.

## Resolution

- `temporal_anchor` was removed because it duplicated `published_at` presence
  as an opaque score.
- `published_at_present` was removed because `published_at` already carries the
  source fact and nullability.
- `factual_density` was removed because it was a weak heuristic, not a verified
  fact-quality signal.

## Related

- `docs/search-signals.md`
- `issues/link-authority-signal-design.md`
