# Search Signals

## Status

Current signal reference.

This document describes the current extraction and document-signal strategy
used by search. It focuses on which signals exist, where they come from, and
how they fit into the current ranking path.

## Related Docs

- [Documentation Guide](./README.md)
- [Architecture](./architecture.md)
- [Search Ranking Policy](./search-ranking-policy.md)

## Problem

Previously, PaleBlueSearch indexed full page text including navigation, footers, and sidebars via `soup.get_text()`. This caused:

1. **Low search relevance** — BM25 matches on boilerplate keywords (nav links, footer text)
2. **Inflated content size** — includes non-content text, making content-shape checks unreliable
3. **Noisy snippets** — search results contain boilerplate fragments
4. **Aggregation pages rank too high** — link-heavy pages (e.g. bookmark listings) have high keyword density

Example: searching "python" returns hatena bookmark listing pages (link collections with high keyword density) instead of docs.python.org.

## Architecture: 3-Layer Signal Stack

```
Layer 3: Search Ranking
         OpenSearch BM25 retrieval
         → source-aware reranking for narrow query classes
         ↑
Layer 2: Signal Scoring (indexer)
         link authority signals
         ↑
Layer 1: Main Content Extraction (crawler)
         trafilatura for boilerplate removal → clean main text + metadata extraction
```

### Layer 1: Main Content Extraction (trafilatura)

Replace `soup.get_text()` with trafilatura (F1=0.958, ACL 2021) for main content extraction.

**Tool selection rationale** (based on SIGIR 2023 benchmark by Bevendorff et al.):

| Tool | F1 | Speed | Japanese | Maintained |
|------|-----|-------|----------|------------|
| **trafilatura** | **0.958** | fast | yes | active |
| readability-lxml | 0.922 | fastest | yes | stable |
| newspaper3k | 0.912 | slow | yes | stale |

**Configuration:**
- `include_comments=True` — forum comments are valuable content (Reddit, HN, SO, 5ch)
- `include_tables=True` — preserve specification tables, comparison data
- `deduplicate=True` — remove repeated navigation text
- `favor_recall=True` — for search, missing content is worse than some boilerplate leaking through

**Fallback:** BeautifulSoup `get_text()` when trafilatura returns None (API docs, SPAs, minimal HTML).

**Impact:** Improves everything downstream — BM25 relevance, snippet quality,
and signal quality.

### Japanese Tokenization

Japanese text is tokenized with SudachiPy before indexing and searching so that
the same analyzer is used at index time and query time.

- implementation lives in `packages/kernel/src/web_search_kernel/analyzer.py`
- the default dictionary is `sudachidict_core`
- tokens are stored in the custom inverted-index tables rather than delegated
  to SQLite FTS or opaque database analyzers
- frontend query parsing and indexer writes both use the same shared logic

### Layer 2: Current Signals

Signals are computed at index time and stored independently rather than pushed
into one large aggregate.

**Current structured signals**

| Signal | Source | Role |
|--------|--------|------|
| `score` | OpenSearch BM25 | lexical relevance score for the returned hit |
| `page_rank` | link graph | page-level link prior |
| `domain_rank` | link graph | domain-level link prior |

**Request-time ranking signals**

| Signal | Source | Role |
|--------|--------|------|
| `canonical_source_match` | URL host/path + canonical source registry | source/domain/path fit |
| `title_intent_match` | query intent terms + result title | precise page-intent fit |
| `path_intent_match` | query intent terms + URL path | precise page-intent fit |
| `comparison_intent_match` | comparison query subjects + title/path/content | comparison-page fit |
| `is_recruiting_page` | URL host/path + title | demotion flag for non-recruiting queries |

**Notes**

- Domain normalization used for result diversity is a grouping key, not a
  ranking signal.

### Layer 3: Search Ranking Integration

The current ranking path is intentionally narrow:

- retrieval uses OpenSearch BM25 over `title_terms^3` and `content_terms`
- `navigational`, `reference`, and a small part of `news` use a narrow source-aware policy
- broad speculative reranking layers were removed
- embedding enrichment is optional metadata for future semantic experiments, not
  part of the baseline retrieval path

This means most document signals are currently exposed as metadata and kept for
index-time analysis, transparency, and future tuning rather than heavy
request-time reranking.

**Metadata passed to API consumers**

| Field | Description |
|-------|-------------|
| `score` | Relevance score for this hit |
| `page_rank` / `domain_rank` | link-based prior signals |

## What We Don't Need (and Why)

| Technique | Why not / Status |
|-----------|-----------------|
| User behavior signals (Navboost) | No user traffic yet |
| SpamBrain-level ML | Overkill for 600K page corpus |
| E-E-A-T evaluation | Not represented by a dedicated ranking signal |
| BrowseRank | Requires browser instrumentation data |

## Current Runtime Notes

- `apps/crawler/src/web_search_crawler/utils/parser.py` uses trafilatura with BS4 fallback.
- `apps/indexer/src/web_search_indexer/services/indexer.py` computes current
  document signals used for storage and ranking policy integration.
- `packages/kernel/src/web_search_kernel/analyzer.py` holds the shared Sudachi-based
  tokenization logic for both indexing and query processing.
- Raw HTML storage is not part of the current runtime. If it becomes important
  again, treat it as a deferred project-plan item rather than current runtime
  behavior.
- The baseline OpenSearch mapping does not contain embedding vectors. If
  semantic retrieval becomes a primary path, split it into an explicit semantic
  index or versioned index design instead of hiding it inside BM25.

### Future

- content_ratio signal (trafilatura text / BS4 full text) — requires crawler-side computation
- Weight tuning based on click-through data
- Re-index existing 600K pages for full effect

## References

- Barbaresi, A. (2021). "Trafilatura: A Web Scraping Library and Command-Line Tool for Text Discovery and Extraction." ACL-IJCNLP 2021 System Demonstrations.
- Kohlschütter, C. et al. (2010). "Boilerplate Detection using Shallow Text Features." WSDM '10.
- Weninger, T. et al. (2010). "CETR: Content Extraction via Tag Ratios." WWW '10.
- Bevendorff, J. et al. (2023). "An Empirical Comparison of Web Content Extraction Algorithms." SIGIR '23.
- Liu, Y. et al. (2008). "BrowseRank: Letting Web Users Vote for Page Importance." SIGIR '08.
- Liu, N.F. et al. (2024). "Lost in the Middle: How Language Models Use Long Contexts." TACL 2024.
- Salemi, A. & Zamani, H. (2024). "Evaluating Retrieval Quality in Retrieval-Augmented Generation." SIGIR '24.
