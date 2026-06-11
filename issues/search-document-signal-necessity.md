# Search Document Signal Necessity

## Problem

The project stores and exposes document-level search signals such as
`factual_density`, but it is not yet clear whether these signals are necessary
enough to justify their runtime and API surface.

This issue is about the signals themselves, not the older field-specific
backfill commands.

## Evidence

- `factual_density` is computed from extracted content.
- It is added to OpenSearch documents by the search projection builder.
- It can be exposed through search result metadata.
- Its direct contribution to ranking quality is not currently proven by an
  evaluation loop.

## Impact

- Search results may expose signals whose meaning is unclear to consumers.
- The projection schema may contain fields that are not needed for retrieval,
  ranking, or operator decisions.
- Keeping weakly justified signals makes search-quality work harder to reason
  about.

## Direction

Decide whether each signal should remain part of the search document model.

For each signal, answer:

- What concrete search or consumer behavior needs this field?
- Is the signal used for ranking, filtering, transparency, or future analysis?
- Is the current name accurate?
- Is the current computation meaningful enough to keep?
- Should it be exposed through public search responses?

If a signal is kept, document its purpose and expected consumer. If not, remove
it from the projection, API response, and related docs.

## Related

- `docs/search-signals.md`
- `issues/link-authority-signal-design.md`
