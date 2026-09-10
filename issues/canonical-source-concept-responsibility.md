# Search Policy and Evaluation Coupling

## Current behavior

`config/canonical_sources.json` supplies source aliases, path/domain preferences,
and retrieval hints to search, and also supplies evaluation cases and judgments.
These are two uses of the same hand-maintained policy data.

The former crawler dependency is gone: current scheduling does not read
`canonical_source`, and `crawl_schedule` was dropped by migration 019. Do not
reopen that removed coupling as a current crawler task.

## Remaining problem

Improving results for source expectations used by the ranker can improve the
reported score without demonstrating better relevance for independent queries.
“Canonical” source fit must not be treated as universal authority or correctness.

Keep configured source regression cases identifiable as such. For a claim about
general search quality or a comparison with vector retrieval, decide on judgments
that are independent of the implementation being compared. The evaluation
limitations are documented in `docs/search-evaluation.md`.
