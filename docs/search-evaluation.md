# Search Evaluation

## Purpose

This document defines a small, explicit search evaluation set for PaleBlueSearch.

The goal is not to prove that search quality is "good" in the abstract, and it
is not to build a must-pass golden test set. The goal is to sample a diverse set
of real search intents and make API-level quality changes visible.

The set should stay small enough to inspect, and each case should prefer explicit
targets over vague quality claims. The baseline expectation is that obvious
navigational queries work and official or primary sources are not systematically
buried.

## Evaluation Data Source

The canonical evaluation set lives in:

- [config/search_eval_cases.json](../config/search_eval_cases.json)

That file is the source of truth for:

- query text
- query type
- target domain/source
- query-specific matching rules

In general, a matched case means the target canonical source appears in the top 3
results and no explicitly bad result appears in the top 3. Use
`judgments` with `relevance` values to keep this small and inspectable:

- `3`: ideal result
- `2`: useful result
- `1`: weakly relevant result
- `0`: unjudged or neutral result
- `-1`: explicitly bad result

The main E2E indicators are `match_rate`, `hit@1`, `hit@3`, and `bad@3`.
Query-type-specific rules should be encoded in the evaluation case itself, not
duplicated here.

Query-class semantics live in [search-ranking-policy.md](./search-ranking-policy.md).
This document is intentionally not the primary data source anymore.
It exists to explain the evaluation policy and how the set is used.

## Evaluation Commands

Run the evaluation set with:

```bash
make evaluate-search
```

Evaluation exit behavior:

- any evaluator runtime error exits non-zero
- case `matched` / `missed` outcomes are observations, not deployment gates

Validate the config before changing it:

```bash
make validate-search-eval
```

## Miss Triage

When an evaluation case is missed, first decide whether the likely cause is
missing coverage, ranking behavior, or a mismatch between the case target and the
assigned query class.
