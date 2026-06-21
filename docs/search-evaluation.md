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

## Evaluation Data Sources

The evaluation runner merges two config sources:

- [config/canonical_sources.json](../config/canonical_sources.json)
- [config/search_eval_cases.json](../config/search_eval_cases.json)

`canonical_sources.json` is the primary source for official-source and reference
queries. It keeps source definitions, canonical domains, generated relevance
judgments, and query-specific matching rules together. This is where obvious
navigational and documentation-style queries should usually live.

`search_eval_cases.json` is the extension set for broader search behavior that
does not belong to one canonical source, such as comparison, overview, and
conceptual queries. It may also define local keyword rules for those added
cases.

Together, the merged evaluation set defines:

- query text
- query type
- target domain/source
- query-specific matching rules

When the same query appears in both sources, the canonical-source case wins and
the later duplicate is ignored.

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

Summarize the evaluation-set distribution without calling the search API:

```bash
make summarize-search-eval
```

To summarize outcomes by query type, first write a JSON report and then pass it
to the summarizer:

```bash
make evaluate-search SEARCH_EVAL_ARGS="--json-output /tmp/search-eval-report.json"
make summarize-search-eval SEARCH_EVAL_REPORT=/tmp/search-eval-report.json
```

Print missed cases with top hits for manual coverage/ranking/eval-rule triage:

```bash
make summarize-search-eval SEARCH_EVAL_REPORT=/tmp/search-eval-report.json SEARCH_EVAL_SUMMARY_ARGS="--show-misses"
```

## Miss Triage

When an evaluation case is missed, first decide whether the likely cause is
missing coverage, ranking behavior, or a mismatch between the case target and the
assigned query class.
