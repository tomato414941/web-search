# Content Quality Strategy

## Problem

PaleBlueSearch indexes full page text including navigation, footers, and sidebars via `soup.get_text()`. This causes:

1. **Low search relevance** — BM25 matches on boilerplate keywords (nav links, footer text)
2. **Inflated word_count** — includes non-content text, making quality metrics unreliable
3. **Noisy snippets** — search results contain boilerplate fragments
4. **Aggregation pages rank too high** — link-heavy pages (e.g. bookmark listings) have high keyword density

Example: searching "python" returns hatena bookmark listing pages (link collections with high keyword density) instead of docs.python.org.

## Architecture: 3-Layer Quality Stack

```
Layer 3: Search Ranking
         BM25(clean content) × authority × content_quality × freshness
         ↑
Layer 2: Content Quality Score (indexer)
         word_count(main text only) + link_density + structure signals
         ↑
Layer 1: Main Content Extraction (crawler)
         trafilatura for boilerplate removal → clean main text
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

Add `content_quality` to OpenSearch `function_score`:

```
score = BM25(clean_content, title^3)
      × (1 + authority × 0.5)       # existing
      × (1 + content_quality × 0.3)  # new
      × freshness_decay              # existing
```

## What We Don't Need (and Why)

| Technique | Why not |
|-----------|---------|
| User behavior signals (Navboost) | No user traffic yet |
| SpamBrain-level ML | Overkill for 600K page corpus |
| E-E-A-T evaluation | Too complex, requires NLP/ML pipeline |
| BrowseRank | Requires browser instrumentation data |

## Implementation Phases

### Phase 1: trafilatura (crawler change only)

- Add trafilatura to crawler/requirements.txt
- Replace `html_to_doc` internals with trafilatura + BS4 fallback
- Return type unchanged: `tuple[str, str, str | None]`
- No indexer/search changes needed — cleaner content improves BM25 immediately

### Phase 2: content_quality score

- Compute content_quality in indexer (trafilatura text vs raw text ratio)
- Add `content_quality` field to OpenSearch mapping
- Store during indexing

### Phase 3: Ranking integration

- Add content_quality to function_score in search.py
- Tune weight parameter (start with 0.3, evaluate)
- Re-index existing pages for full effect

## References

- Barbaresi, A. (2021). "Trafilatura: A Web Scraping Library and Command-Line Tool for Text Discovery and Extraction." ACL-IJCNLP 2021 System Demonstrations.
- Kohlschütter, C. et al. (2010). "Boilerplate Detection using Shallow Text Features." WSDM '10.
- Weninger, T. et al. (2010). "CETR: Content Extraction via Tag Ratios." WWW '10.
- Bevendorff, J. et al. (2023). "An Empirical Comparison of Web Content Extraction Algorithms." SIGIR '23.
- Liu, Y. et al. (2008). "BrowseRank: Letting Web Users Vote for Page Importance." SIGIR '08.
- Liu, N.F. et al. (2024). "Lost in the Middle: How Language Models Use Long Contexts." TACL 2024.
- Salemi, A. & Zamani, H. (2024). "Evaluating Retrieval Quality in Retrieval-Augmented Generation." SIGIR '24.
