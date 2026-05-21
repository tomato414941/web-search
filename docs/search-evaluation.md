# Search Evaluation

## Purpose

This document defines a small, explicit search evaluation set for PaleBlueSearch.

The goal is not to prove that search quality is "good" in the abstract.
The goal is to make quality regressions and obvious ranking failures visible.

The set should stay small enough to inspect, and each case should prefer explicit
expected outcomes over vague quality claims.
The baseline expectation is that obvious navigational queries work and official
or primary sources are not systematically buried.

## Evaluation Data Source

The canonical evaluation set lives in:

- [config/search_eval_cases.json](../config/search_eval_cases.json)

That file is the source of truth for:

- query text
- query type
- tier
- expected domain/source
- query-specific pass/fail rules

In general, a passing result means the expected canonical source appears in the
top 3 results. Query-type-specific rules should be encoded in the evaluation
case itself, not duplicated here.

Query-class semantics live in [search-ranking-policy.md](./search-ranking-policy.md).
This document is intentionally not the primary data source anymore.
It exists to explain the evaluation policy and how the set is used.

## Evaluation Commands

Run the evaluation set with:

```bash
make evaluate-search
```

Run only tier-1 with:

```bash
make evaluate-search-tier1
```

Evaluation exit behavior:

- any evaluator runtime error exits non-zero
- any tier-1 `fail` exits non-zero
- tier-2 `fail` remains visible but non-blocking in the full report
- `warning` remains non-blocking

Validate the config before changing it:

```bash
make validate-search-eval
```

## Failure Triage

When an evaluation case fails, first decide whether the likely cause is missing
coverage, ranking behavior, or a mismatch between the case expectation and the
assigned query class.
