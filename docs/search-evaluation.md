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

## Minimum Golden Query Set

These queries should be checked manually and reused over time.

| Query | Type | Expected top result or domain | Notes |
|---|---|---|---|
| `Google` | navigational | `google.com` | Official homepage should be first |
| `GitHub` | navigational | `github.com` | Official homepage should be first |
| `FastAPI docs` | navigational | `fastapi.tiangolo.com` | Official docs should beat tutorials |
| `OpenAI API` | navigational | `developers.openai.com` or official OpenAI docs | Official API docs should be first |
| `Python documentation` | reference | `docs.python.org` | Official docs should be first |
| `PostgreSQL jsonb` | reference | `postgresql.org` docs | Official docs should rank very high |
| `FastAPI background tasks` | reference | `fastapi.tiangolo.com` docs | Official docs should beat blog posts |
| `What is BM25` | overview/reference | a BM25-focused explanatory source | Top 3 should explicitly mention BM25 |
| `site reliability engineering` | overview/reference | canonical or explanatory SRE sources | Top 3 should include at least two strong SRE sources |
| `pytest fixture not found` | reference/troubleshooting | `docs.pytest.org` | Official pytest docs should be in top 3 |
| `docker compose orphan containers` | reference/troubleshooting | `docs.docker.com` | Official Docker docs should be in top 3 |
| `FastAPI vs Django` | comparison | a page that explicitly compares FastAPI and Django | Top 3 should include a result that names both FastAPI and Django |
| `OpenSearch vs Elasticsearch` | comparison | a page that explicitly compares OpenSearch and Elasticsearch | Top 3 should include a result with both names and a comparison cue |
| `OpenAI news` | news | recent official or primary reporting | Recency and source quality matter |
| `Python 3.13 release` | news/reference | `docs.python.org` release notes | Official release page should rank high |

## Pass Criteria

For now, use a simple manual rubric.

### Navigational

- Pass: the official destination is rank 1
- Warning: the official destination is in ranks 2-3
- Fail: the official destination is below rank 3 or missing

### Reference

- Pass: official or canonical documentation is in ranks 1-3
- Fail: unofficial summaries consistently outrank official docs without a clear reason

### Overview / Troubleshooting / Comparison / News

- Pass: the top results are useful for the query type
- Fail: the top results are generic, stale, thin, or mismatched to intent

## Current Product Expectation

At minimum, PaleBlueSearch should satisfy two baseline expectations:

1. Obvious navigational queries should work.
2. Official or primary sources should not be systematically buried.

If those fail, more advanced ranking ideas do not matter yet.

## Next Step

Once this document is stable, add a lightweight evaluation workflow:

- run the query set against production or staging
- record top 3 results
- mark pass / warning / fail
- track changes when ranking logic changes
