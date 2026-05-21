# Tier 1 GitHub Navigational Failure

## Status

Closed.

## Problem

The production Tier 1 search evaluation is not green. The `GitHub`
navigational query fails because the official GitHub homepage is missing from
the top 3 results.

## Evidence

`make evaluate-search-tier1` against production returned:

```text
Summary
  pass=35 warning=0 fail=1 manual=0 errors=0
Gate
  blocking tier-1 failures detected
```

The failing case was:

```text
[FAIL] GitHub
  type=navigational tier=1
  expected=github.com
  reason=official destination missing from top 3
```

Observed top 3:

```text
1. https://www.github.com/pentacent/keila
2. https://www.github.com/waldronlab/presentations
3. https://www.github.com/hellovai
```

## Impact

- `docs/search-evaluation.md` defines Tier 1 as the production baseline, but
  it is not green right now.
- Navigational search quality has a visible hole for a major site.
- This weakens confidence in baseline search behavior.

## Direction

Determine whether this is an index coverage problem or a ranking/retrieval
problem.

Initial checks:

- Confirm whether `https://github.com/` or `http://github.com/` exists in the
  production index.
- If present, inspect why repo pages outrank the homepage.
- If absent, trace crawl coverage and canonical URL handling for GitHub.

## Resolution

This was not a GitHub crawl coverage problem. The GitHub homepage existed in
PostgreSQL and OpenSearch, but a subset of OpenSearch documents written through
bulk indexing used `title_tokens` and `content_tokens` instead of the searchable
`title` and `content` fields.

Fixes:

- Changed bulk OpenSearch document construction to write `title` and `content`.
- Added a regression test to prevent `title_tokens` / `content_tokens` from
  reappearing in bulk OpenSearch documents.
- Repaired the existing production OpenSearch documents affected by the field
  drift.
- Removed the temporary repair command after the production repair completed.

Production verification:

```text
Malformed OpenSearch search-field documents: 312486 -> 0
GitHub search result: https://github.com/ rank 1
Tier 1 search evaluation: pass=36 warning=0 fail=0 manual=0 errors=0
```
