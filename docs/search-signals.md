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
- a 1,024-dimensional embedding of title and bounded content.

`content_terms` is built from the same truncated content. A passage beyond the
limit cannot match through body terms even if it exists in PostgreSQL. The
search API's inline content is also bounded; the by-URL content API reads the
full stored text.

The analyzer is shared between indexing and querying. There are no current
custom inverted-index tables in PostgreSQL. OpenSearch handles BM25 retrieval.
Some hosts and account/login paths are excluded from the projection by
`packages/search-config/src/web_search_search_config/index_exclusions.py`.
A stored document therefore need not be a searchable document.

## Semantic representation

Document and query embeddings use `perplexity/pplx-embed-v1-0.6b` via OpenRouter.
The document input is title plus the bounded content above, truncated to 31,999
tokens using the pinned Perplexity tokenizer. The API receives text strings, not
token IDs from another model. Long pages currently have one vector; later passages
can therefore be absent from both lexical and semantic retrieval. This is a
representation limit, not something RRF can repair.

Vectors are stored only in OpenSearch. There is no separate PostgreSQL embedding
table in the active implementation. Embedding errors fail indexing/search rather
than silently selecting another retrieval path.

The public score is OpenSearch's RRF score. Source-specific ranking rules and
link-rank projection have been removed. See `search-ranking-policy.md`.
