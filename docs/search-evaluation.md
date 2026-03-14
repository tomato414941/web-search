# Search Evaluation

## Purpose

This document defines a small, explicit search evaluation set for PaleBlueSearch.

The goal is not to prove that search quality is "good" in the abstract.
The goal is to make quality regressions and obvious ranking failures visible.

## Why This Exists

PaleBlueSearch already has ranking features such as:

- lexical retrieval
- source-oriented ranking signals
- canonical source promotion

But having ranking machinery is not the same as having strong search quality.

We need a simple reference set that answers questions like:

- Does a navigational query return the official site first?
- Does a reference query return authoritative documentation?
- Does a comparison query return pages that actually compare things?
- Does a news query avoid stale or generic background pages?

## Current Scope

PaleBlueSearch currently treats these query classes as the primary product scope:

- navigational
- reference

These classes should be held to a higher standard and are expected to pass.

The following classes are still evaluated, but they are not yet considered first-class product scope:

- comparison
- news
- exploratory reference gaps outside the current release baseline

They remain in the golden set as visibility checks, not as current release gates.

## Evaluation Principles

1. Start small.
   A small query set that people actually inspect is better than a large set nobody maintains.

2. Prefer explicit expected winners.
   For some queries, the expected top result should be obvious.

3. Separate query types.
   Navigational, reference, overview, troubleshooting, comparison, and news queries should not be judged the same way.

4. Judge usefulness, not only topical overlap.
   A page can mention the right words and still be a bad result.

## Query Types

- Navigational: the user wants the official site or canonical destination
- Reference: the user wants official docs or a precise technical source
- Overview: the user wants a good high-level explanation
- Troubleshooting: the user wants a fix or diagnosis path
- Comparison: the user wants trade-offs between alternatives
- News: the user wants recent, source-grounded updates

## Evaluation Data Source

The canonical evaluation set lives in:

- [config/search_eval_cases.json](../config/search_eval_cases.json)

That file is the source of truth for:

- query text
- query type
- tier
- expected domain/source
- query-specific pass/fail rules

This document is intentionally not the primary data source anymore.
It exists to explain the evaluation policy and how the set is used.

## Current Set Shape

The current evaluation set contains:

- tier-1 navigational/reference baseline queries
- tier-2 comparison/news visibility queries
- tier-2 exploratory reference coverage checks for additional ecosystems

At the current stage:

- tier-1 is the release-relevant baseline
- tier-2 remains visible but non-blocking

Run the current set with:

```bash
make evaluate-search
```

Run only tier-1 with:

```bash
make evaluate-search-tier1
```

Validate the config before changing it:

```bash
make validate-search-eval
```

## Pass Criteria

For now, use a simple manual rubric.

### Navigational

- Pass: the official destination is rank 1
- Warning: the official destination is in ranks 2-3
- Fail: the official destination is below rank 3 or missing

### Reference

- Pass: official or canonical documentation is in ranks 1-3
- Fail: unofficial summaries consistently outrank official docs without a clear reason

### Overview / Troubleshooting

- Pass: the top results are useful for the query type
- Fail: the top results are generic, stale, thin, or mismatched to intent

### Comparison / News

- Pass: the top results are useful for the query type
- Fail: the top results are generic, stale, thin, or mismatched to intent

## Current Product Expectation

At minimum, PaleBlueSearch should satisfy two baseline expectations:

1. Obvious navigational queries should work.
2. Official or primary sources should not be systematically buried.

If those fail, more advanced ranking ideas do not matter yet.

At the current stage, comparison, news, and exploratory reference expansion remain visible stretch goals rather than release-blocking scope.

## Tier-2 Work Trigger

Tier-2 failures should not be addressed ad hoc.
They become active work only when one of the following is true:

1. The tier-1 baseline passes in production across 3 consecutive production changes that affect search behavior.
   A qualifying change is any production deployment that touches search, crawler, indexer, or retrieval/ranking code.
   "Passes" means every tier-1 query in the current golden set is still passing at production after the deploy.
2. Product scope is explicitly expanded to include comparison, news, or additional reference coverage quality.
   This should be a deliberate decision, not a side effect of unrelated ranking work.

Until one of those conditions is met, tier-2 failures remain visible but non-blocking.

If tier-2 work starts, the default order is:

1. additional reference coverage gaps
2. comparison queries
3. news queries

News comes later because it requires source and recency policy, which is broader than the current narrow ranking scope.

## Tier-1 Stability Tracking

Track search-affecting production changes here.

A row should be added only when a production deployment changes search behavior.
This includes changes to search query handling, ranking, retrieval, crawler coverage, indexing behavior, or canonical source policy.

For each qualifying deployment:

1. run `make evaluate-search` against production
2. record whether all tier-1 queries passed
3. update the tier-1 streak

The tier-1 streak resets to `0/3` on any tier-1 failure.
It advances only when a qualifying production change still passes the full tier-1 set.

| Date | Commit | Change Summary | Tier-1 Result | Tier-1 Streak |
|---|---|---|---|---|
| 2026-03-09 | `5feba37` | Defined explicit tier-2 trigger policy | Baseline rule created; streak starts here | `0/3` |

## Next Step

Once this document is stable, add a lightweight evaluation workflow:

- run the query set against production or staging
- record top 3 results
- mark pass / warning / fail
- track changes when ranking logic changes
