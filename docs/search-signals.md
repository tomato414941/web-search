# Indexed content and ranking signals

This document records what information reaches search and what can be lost
between fetching a page and returning a result.

## Extraction

The crawler uses trafilatura for main text, with comments and tables enabled,
deduplication enabled, and recall favored. If extraction returns no text, it
uses BeautifulSoup text after removing scripts, styles, and noscript elements.
The fallback can retain navigation or other boilerplate.

Raw HTML is not stored by the current pipeline. Changing extraction cannot be
applied to historical HTML locally; affected pages must be fetched again.
Publication dates, author identity, `temporal_anchor`, and `factual_density` are
not current search-result signals. Do not infer those guarantees from older
product descriptions.

## Document store and search projection

PostgreSQL stores the full extracted text. OpenSearch stores:

- title, URL, host, and path;
- the first 20,000 characters of extracted content;
- `title_terms` and `content_terms`, tokenized with the shared Sudachi analyzer;
- the link-rank values available when the document is projected.

`content_terms` is built from the same truncated content. A passage beyond the
limit cannot match through body terms even if it exists in PostgreSQL. The
search API's inline content is also bounded; the by-URL content API reads the
full stored text.

The analyzer is shared between indexing and querying. There are no current
custom inverted-index tables in PostgreSQL. OpenSearch handles BM25 retrieval.
Some hosts and account/login paths are excluded from the projection by
`packages/search-config/src/web_search_search_config/index_exclusions.py`.
A stored document therefore need not be a searchable document.

## Link-rank freshness

The Web model maintenance worker computes PageRank and domain rank from stored
links and writes PostgreSQL rank tables. Indexing or rebuilding the projection
copies those values into OpenSearch.

Recalculating ranks alone does not update existing search documents. When a
rank change should affect search, project it and then verify the returned
ordering. The quality and refresh questions remain open in
`issues/link-authority-signal-design.md`.

## Request-time signals

Source fit, title/path fit, comparison fit, and recruiting-page detection are
computed from the query and retrieved candidates. They are internal policy
inputs, not independently validated measures of relevance. Their precedence is
specified in `search-ranking-policy.md`.

The public `score` is an OpenSearch score; `page_rank` and `domain_rank` are
stored link priors. None is a probability that the page answers the query.
Optional embedding backfill is separate from this projection and does not make
vector retrieval available in the serving API.
