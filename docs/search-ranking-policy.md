# Search Ranking Policy

## Status

Current design policy.

This document describes the current retrieval and ranking policy for search.
It uses the vocabulary defined in [search-concepts.md](./search-concepts.md)
and stays below that conceptual layer.

## Purpose

The goal of this policy is to preserve a small, explainable ranking path while
improving baseline search quality.

The current priority is not broad semantic ranking.
The current priority is that navigational, reference, and narrow
news/reference queries can surface official or primary sources without hiding
the user's concrete query intent.

## Non-Goals

- Do not introduce broad speculative reranking.
- Do not turn news handling into a general freshness ranking system.
- Do not use the canonical source registry as a per-query winner table.
- Do not add query-specific hacks across multiple layers.
- Do not change crawler frontier planning, indexing, or document-signal
  extraction in this policy.

## Query Classes

This policy currently uses five small query classes:

- `navigational`
- `reference`
- `news`
- `comparison`
- `other`

The classifier should stay rule-based and small.
If a query cannot be classified confidently, it should fall back to `other`.

### Navigational

Queries that primarily seek an official site or canonical destination.

Examples:

- `Google`
- `GitHub`
- `FastAPI docs`
- `OpenAI API`

### Reference

Queries that primarily seek canonical technical documentation or a precise
technical source.

Examples:

- `Python documentation`
- `PostgreSQL jsonb`
- `FastAPI background tasks`

### News

Only narrow source-aware handling is allowed here.

Examples:

- `OpenAI news`
- `Python 3.13 release`

This is limited to lightweight official-source handling.
It is not a general recency or freshness framework.

Known exception:

- `OpenAI news`
- `OpenAI announcements`

These are evaluated as visibility checks because direct article fetches on
`openai.com` can hit Cloudflare challenge responses on the crawler's non-browser
fetch path. Misses here may therefore be source fetchability failures rather
than pure ranking failures.

### Comparison

Only a narrow intent-aware rerank is allowed here.

Examples:

- `FastAPI vs Django`
- `OpenSearch vs Elasticsearch`

The policy may promote pages that explicitly compare both subjects and reduce
same-domain duplication when it crowds out useful alternatives.

### Other

Everything else.

This class should keep the simplest ranking behavior.

## Canonical Source Registry

The canonical source registry maps products or ecosystems to canonical domains
and optional preferred paths.

It is a source policy table, not a per-query winner table.

Rules:

- prefer source-level domains and path prefixes over individual query winners
- keep entries explicit in config
- keep the registry small enough to reason about
- use preferred paths only when they describe stable source structure

## Retrieval Policy

Retrieval creates the candidate set.
Ranking and reranking can only order candidates that retrieval returns.

Current retrieval behavior:

- BM25 through OpenSearch is the default retrieval path.
- Query parsing supports `site:`, exact phrases, and exclude terms.
- Source-aware queries may pass canonical domain/path hints to OpenSearch.
- Source-restricted queries may filter retrieval to known canonical domains.
- Comparison queries may add subject and comparison-cue boosts to OpenSearch
  retrieval so explicit comparison pages are more likely to enter the candidate
  set.

`retrieval_query` is allowed only as a narrow retrieval aid.
It must not erase concrete user intent.

For example, a broad docs-home query may use a stable source-oriented retrieval
query. A precise reference query should preserve its concrete feature or API
terms. Rewriting a precise query into a generic docs query is a retrieval
failure risk.

## Ranking And Reranking Policy

The current implementation is intentionally narrow but not yet the ideal final
shape.

Current ranking behavior:

- OpenSearch produces the initial BM25 score and may apply canonical host/path
  boosts.
- The frontend builds search hits from OpenSearch candidates.
- A post-retrieval rerank may use link ranks, canonical source/path matches,
  title/path intent matches, comparison intent, and recruiting-page demotion.

This means ranking is currently split across OpenSearch query scoring and
Python post-rerank logic.
That is acceptable as the current implementation, but it should not grow into a
hidden second ranking system.

The post-retrieval rerank should keep signals explicit:

- `canonical_source_match`: official or primary source fit
- `title_intent_match`: concrete query terms matched in the title
- `path_intent_match`: concrete query terms matched in the URL path
- `comparison_intent_match`: explicit fit for comparison queries
- `is_recruiting_page`: demotion flag for non-recruiting queries

Future ranking work should preserve this shape:

- expose the signals used for ranking
- combine signals in one understandable policy layer
- avoid hidden aggregate scores whose inputs are hard to explain
- keep retrieval failures separate from ranking failures

## Guardrails

- Do not solve retrieval failures by adding more ranking rules.
- Do not use generic `retrieval_query` values for precise reference queries.
- Do not add broad freshness ranking under the `news` class.
- Do not let comparison reranking affect non-comparison queries.
- Do not treat source authority as a single opaque aggregate when underlying
  link signals can remain separate.
- Keep evaluation acceptance criteria in
  [search-evaluation.md](./search-evaluation.md).

## Relationship To Evaluation

This policy describes how search should retrieve and rank candidates.
It does not define the golden set.

The evaluation set and failure classification live in
[search-evaluation.md](./search-evaluation.md).

When a search case fails, classify it before changing this policy:

- expected target missing from the index or candidate set: coverage or retrieval
  failure
- expected target present but ranked too low: scoring or ranking failure
- expectation disagrees with current query class: policy mismatch

## Follow-Up Direction

The next substantial ranking improvement should be a small, explicit scoring
model for reranking candidates.

That work should make individual signals visible and tunable before adding new
signals or heavier semantic methods.
