# Search Ranking Policy

## Status

Current.

This document defines the current narrow ranking policy after the recent search simplification work.

## Problem

PaleBlueSearch still fails baseline queries such as:

- `Google`
- `GitHub`
- `FastAPI docs`
- `OpenAI API`
- `PostgreSQL jsonb`

The current problem is no longer only index coverage.
For some queries, the canonical page exists in the index but still does not rank high enough.

## Goal

Fix the minimum baseline for navigational and reference queries without reintroducing broad speculative reranking.

## Non-Goals

- Do not redesign ranking for comparison queries in this change.
- Do not turn news handling into a broader freshness ranking system in this change.
- Do not add a large site-specific whitelist with query-specific hacks.
- Do not reintroduce heavy post-retrieval reranking layers such as the removed scope-match and claim-diversity logic.
- Do not change crawler queueing, indexing, or document quality scoring in this change.

## Query Classes

This policy introduces four small query classes:

- `navigational`
- `reference`
- `news`
- `other`

The classifier should stay rule-based and small.

### Navigational

Queries that primarily seek an official site or canonical destination.

Examples:

- `Google`
- `GitHub`
- `FastAPI docs`
- `OpenAI API`

Heuristics:

- short query
- brand or product-like name
- optional suffixes such as `docs`, `documentation`, `api`, `homepage`, `official`

### Reference

Queries that primarily seek canonical technical documentation or a precise technical source.

Examples:

- `Python documentation`
- `PostgreSQL jsonb`
- `FastAPI background tasks`

Heuristics:

- mentions of a product, library, or platform plus a technical feature or concept
- explicit doc-like suffixes such as `reference`, `documentation`, `docs`

### Other

Everything else.

This class must keep the current simpler ranking behavior.

### News

Only narrow source-aware handling is allowed here.

Examples:

- `OpenAI news`
- `Python 3.13 release`

This is currently limited to lightweight official-source promotion.
It is not a general freshness or recency ranking framework.

## Canonical Source Registry

Introduce a small registry of canonical sources.

The registry is not a per-query winner table.
It is a source policy table that maps products or ecosystems to canonical domains and optional preferred paths.

Examples:

- `google` -> `google.com`
- `github` -> `github.com`
- `fastapi` -> `fastapi.tiangolo.com`
- `openai api` -> `developers.openai.com`
- `python documentation` -> `docs.python.org`
- `postgresql` -> `postgresql.org`

Rules:

- keep it small
- use domains, not individual query strings, as the primary key where possible
- allow optional preferred path prefixes for docs-heavy sites
- keep it explicit in code or config, not inferred from content heuristics alone

## Ranking Rule

Apply this policy primarily to `navigational` and `reference` queries.
Use `news` only for narrow official-source promotion.

### Retrieval

Keep the current retrieval step simple.

- BM25 remains the default retrieval path
- existing query parsing such as `site:`, exact phrases, and exclude terms remains unchanged
- no new complex OpenSearch query-time scoring layer should be introduced in this change

### Thin Canonical Boost

After retrieval, apply a single thin rerank pass:

- detect whether each hit matches a canonical domain or preferred path for the query
- add a small, explicit canonical boost
- preserve original retrieval order among non-canonical hits

This should be implemented as a stable rerank, not as a full second ranking system.

For some narrow source-aware cases, retrieval may also receive a small canonical host/path hint so that official pages can enter the candidate set at all.

### Guardrails

- canonical boost applies mainly to `navigational` and `reference`
- `news` is allowed only when it points to a small official source set
- canonical boost should not reorder canonical hits among themselves except by original score
- canonical boost should be strong enough to move the official destination into the top 3 for baseline queries
- canonical boost should not require document body inspection

## Acceptance Criteria

This policy is successful if the following improve on the golden query set in [search-evaluation.md](./search-evaluation.md):

- `Google` -> `google.com` in top 3
- `GitHub` -> `github.com` in top 3
- `FastAPI docs` -> `fastapi.tiangolo.com` in top 3
- `OpenAI API` -> `developers.openai.com` in top 3
- `PostgreSQL jsonb` -> `postgresql.org` docs in top 3

At this stage, top 1 is desirable but not required.
Top 3 is the minimum bar.

Comparison and broader news quality remain outside the main acceptance scope for now.

## Implementation Constraints

- keep the classifier and registry in one small module
- keep the rerank logic in one small post-retrieval step
- avoid query-specific conditionals spread across multiple layers
- if a query cannot be classified confidently, fall back to `other`

## Follow-Up

If this policy improves baseline navigational and reference behavior, only then consider:

- expanding the canonical registry
- refining classification heuristics
- adding targeted handling for troubleshooting queries

If it does not improve the baseline enough, revisit retrieval and corpus coverage before adding more ranking logic.
