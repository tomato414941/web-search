# Search evaluation

The current evaluator observes a small configured set of search cases. It is
useful for diagnosing changes to those cases, but is not an independent
benchmark of general Web search quality or a mandatory deployment gate.

## Cases and judgments

The runner merges `config/canonical_sources.json` and
`config/search_eval_cases.json`. Canonical-source cases win duplicate query
names. The first file is also used by ranking, so evaluation and implementation
are not independent: improving this score can reflect better agreement with
hand-written source expectations rather than better answers for users.

Cases use URL/domain/path/title rules and relevance judgments. Values are:

| Value | Meaning |
|---|---|
| 3 | Ideal result |
| 2 | Useful result |
| 1 | Weakly relevant result |
| 0 | Unjudged or neutral result |
| -1 | Explicitly bad result |

A zero label does not establish that a result is irrelevant. `matched` uses
case-specific expectations; inspect the case before treating a miss as a ranking
bug. Some source-fetchability cases are observations rather than ordinary
ranking requirements.

## Run and inspect

Run from the repository root after `make sync`:

```bash
make validate-search-eval
make summarize-search-eval
make evaluate-search SEARCH_EVAL_BASE_URL=http://localhost:8083 \
  SEARCH_EVAL_ARGS="--limit 10 --json-output /tmp/search-eval-report.json"
make summarize-search-eval SEARCH_EVAL_REPORT=/tmp/search-eval-report.json \
  SEARCH_EVAL_SUMMARY_ARGS="--show-misses"
```

Without `SEARCH_EVAL_BASE_URL`, the Makefile targets the public service.
The CLI fetches only three results by default. Request at least ten before
interpreting `ndcg@10`; the JSON report's displayed `top_hits` still contains
only the first three results.

Runtime exceptions make the evaluator exit nonzero. `matched` and `missed`
outcomes do not. A zero exit status is not a quality pass.

## Metric limitations

- `hit@1`, `hit@3`, MRR, and NDCG use the configured relevance rules; they do not
  provide independent judgments of arbitrary pages.
- For cases whose judgments are all exact URLs, NDCG's ideal ordering comes
  from those judgments. Otherwise, the implementation derives it by sorting
  the relevances of the returned hits. In the latter case, a high NDCG does not
  demonstrate that missing relevant pages were retrieved.
- The API can return HTTP 200 with `degraded: true`. The evaluator currently
  does not classify that flag as a transport/runtime failure and can record it
  as a missed case. Check the API response and dependency health when many cases
  suddenly miss.
- Coverage, index state, and query rewriting affect the outcome before
  reranking. A missing indexed page and a poorly ordered candidate are different
  problems.

## Compare a proposed retrieval method

Keep the corpus/index snapshot, query set, judgments, result depth, and request
configuration fixed, and record which code/config revisions were used. Compare
quality together with latency and operating cost. If judgments or the corpus
change between runs, the score difference cannot be attributed to the algorithm
alone.

The current source-oriented cases can reveal regressions in those behaviors.
They cannot, by themselves, settle whether BM25, dense retrieval, or a hybrid is
best for the intended general-purpose search product.
