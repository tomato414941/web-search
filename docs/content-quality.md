# Content Quality Strategy

## Problem

Previously, PaleBlueSearch indexed full page text including navigation, footers, and sidebars via `soup.get_text()`. This caused:

1. **Low search relevance** — BM25 matches on boilerplate keywords (nav links, footer text)
2. **Inflated word_count** — includes non-content text, making quality metrics unreliable
3. **Noisy snippets** — search results contain boilerplate fragments
4. **Aggregation pages rank too high** — link-heavy pages (e.g. bookmark listings) have high keyword density

Example: searching "python" returns hatena bookmark listing pages (link collections with high keyword density) instead of docs.python.org.

## Architecture: 3-Layer Quality Stack

```
Layer 3: Search Ranking
         OpenSearch BM25 retrieval
         → thin canonical-source promotion for narrow query classes
         ↑
Layer 2: Signal Scoring (indexer)
         factual_density + temporal_anchor + authorship_clarity + information_origin
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

**Impact:** Improves everything downstream — BM25 relevance, word_count accuracy, snippet quality, quality scoring.

### Layer 2: Content Quality Score

Computed at index time, stored in OpenSearch. Based on Boilerpipe's "shallow text features" (Kohlschütter 2010, WSDM).

**Signals:**

| Signal | Source | Rationale |
|--------|--------|-----------|
| Main text word count (log scale) | trafilatura output | Substantial content vs thin pages |
| Content ratio (main / full text) | trafilatura vs BS4 | High ratio = content-rich; low ratio = boilerplate-heavy |
| Link density (outlinks / words) | existing data | High density = aggregation/link list page |
| Title quality | existing data | Presence and reasonable length |
| Has structured metadata | published_at | Structured content tends to be higher quality |

**Formula sketch:**

```python
def content_quality(main_words, raw_words, outlinks, title, has_published_at):
    text_score = min(1.0, log10(main_words + 1) / 3.0)
    content_ratio = main_words / max(raw_words, 1)
    link_density = outlinks / max(main_words, 1)
    link_penalty = max(0.3, 1.0 - link_density * 3)
    structure_bonus = 1.0 + (0.1 if len(title) > 5 else 0) + (0.1 if has_published_at else 0)
    return text_score * content_ratio * link_penalty * structure_bonus
```

### Layer 3: Search Ranking Integration

The current ranking path is intentionally narrow:

- retrieval uses OpenSearch BM25 over `title^3` and `content`
- `navigational`, `reference`, and a small part of `news` use a thin canonical-source policy
- broad speculative reranking layers were removed

This means most document-quality signals are currently exposed as metadata and kept for index-time analysis, transparency, and future tuning rather than heavy request-time reranking.

**Metadata passed to API consumers**

| Field | Description |
|-------|-------------|
| `authorship_clarity` | Author/org presence score (0.0-1.0) |
| `author` / `organization` | Extracted from HTML metadata (JSON-LD, meta tags) |
| `origin_type` | spring / river / delta / swamp |

## What We Don't Need (and Why)

| Technique | Why not / Status |
|-----------|-----------------|
| User behavior signals (Navboost) | No user traffic yet |
| SpamBrain-level ML | Overkill for 600K page corpus |
| E-E-A-T evaluation | Partially addressed by `authorship_clarity` (rule-based, no ML) |
| BrowseRank | Requires browser instrumentation data |

## Implementation Status

### Phase 1: trafilatura — DONE

- trafilatura added to `crawler/requirements.txt`
- `html_to_doc` uses trafilatura with BS4 fallback (`crawler/src/app/utils/parser.py`)
- Options: `include_comments=True`, `include_tables=True`, `deduplicate=True`, `favor_recall=True`

### Phase 2: content_quality score + ranking — DONE (superseded by later simplification)

- `_compute_content_quality()` in `indexer/src/app/services/indexer.py`
- `content_quality` float field retained in OpenSearch for backward compatibility
- Ranking now uses `factual_density` instead of `content_quality`

### Phase 3: HTML storage for offline re-processing — DESIGN DONE

- Design document: [html-storage.md](./html-storage.md)
- Cloudflare R2 for raw HTML storage ($0.14/mo)
- Enables re-processing without re-crawling

### Phase 4: source-oriented document signals — DONE

- `temporal_anchor` replaces freshness decay (`indexer/src/app/services/indexer.py`)
- `authorship_clarity` + author/org extraction (`crawler/src/app/utils/parser.py`)
- `factual_density` replaces content_quality in scoring (`shared/src/shared/search_kernel/factual_density.py`)
- `information_origin` replaces PageRank (`shared/src/shared/search_kernel/information_origin.py`)
- DB migrations: 008 (authorship metadata), 009 (information_origins table)

### Phase 5: Result-set intelligence — REMOVED

- Query-intent reranking and claim-clustering were removed.
- The search flow now stays closer to BM25 retrieval order until stronger evidence justifies reintroducing post-retrieval ranking.

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
