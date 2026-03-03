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
         OpenSearch function_score (origin_score, factual_density, temporal_anchor)
         → Scope Match re-ranking → Claim Diversity clustering
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

The ranking pipeline applies scoring signals in two phases:

**Phase A — OpenSearch `function_score` (retrieval-time)**

```
score = BM25(clean_content, title^3) × Σ weighted signals
```

| Signal | Field | Weight | Description |
|--------|-------|--------|-------------|
| Information Origin | `origin_score` | 1.0 | Primary source > aggregation (replaces PageRank) |
| Factual Density | `factual_density` | 0.3 | Verifiable facts per unit of text (replaces content_quality) |
| Temporal Anchor | `temporal_anchor` | 0.1 | Temporal transparency — has `published_at`? (replaces freshness decay) |

Scoring uses `score_mode: sum`, `boost_mode: multiply`. See `shared/src/shared/opensearch/search.py`.

**Phase B — Post-retrieval re-ranking**

1. **Scope Match**: Boost results where document type matches query intent (±20%). Intents: overview, tutorial, troubleshoot, reference, news, comparison. See `shared/src/shared/search_kernel/scope_match.py`.
2. **Claim Diversity**: Cluster results by content similarity (TF-IDF cosine), pick best representative per cluster (origin_score × factual_density). Replaces domain-only diversity cap. See `shared/src/shared/search_kernel/claim_diversity.py`.

**Metadata passed to API consumers (not used in scoring)**

| Field | Description |
|-------|-------------|
| `authorship_clarity` | Author/org presence score (0.0-1.0) |
| `author` / `organization` | Extracted from HTML metadata (JSON-LD, meta tags) |
| `origin_type` | spring / river / delta / swamp |
| `cluster_id` / `sources_agreeing` | Claim cluster metadata |
| `confidence` | Result-set confidence (high / low / contested) |
| `query_intent` | Detected query intent |

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

### Phase 2: content_quality score + ranking — DONE (superseded by Phase 4)

- `_compute_content_quality()` in `indexer/src/app/services/indexer.py`
- `content_quality` float field retained in OpenSearch for backward compatibility
- Ranking now uses `factual_density` instead of `content_quality`

### Phase 3: HTML storage for offline re-processing — DESIGN DONE

- Design document: [html-storage.md](./html-storage.md)
- Cloudflare R2 for raw HTML storage ($0.14/mo)
- Enables re-processing without re-crawling

### Phase 4: AI-agent-optimized ranking signals — DONE

- `temporal_anchor` replaces freshness decay (`indexer/src/app/services/indexer.py`)
- `authorship_clarity` + author/org extraction (`crawler/src/app/utils/parser.py`)
- `factual_density` replaces content_quality in scoring (`shared/src/shared/search_kernel/factual_density.py`)
- `information_origin` replaces PageRank (`shared/src/shared/search_kernel/information_origin.py`)
- DB migrations: 008 (authorship metadata), 009 (information_origins table)

### Phase 5: Result-set intelligence — DONE

- `claim_diversity` replaces domain-only diversity (`shared/src/shared/search_kernel/claim_diversity.py`)
- `scope_match` for query intent × document type matching (`shared/src/shared/search_kernel/scope_match.py`)

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
