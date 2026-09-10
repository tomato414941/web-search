# Hybrid retrieval

The serving path uses OpenSearch's native `hybrid` query and RRF search pipeline.
There is no Python reranking, source-specific query rewriting, or BM25-only mode.
The product remains general-purpose Web search.

## Representation and retrieval

The shared Sudachi analyzer prepares title/body terms and lexical queries.
`text-embedding-3-small` generates 1,536-dimensional vectors for document title
plus bounded content, and for the user's positive query text. Both use the same
model and tokenizer. Input is capped at 8,191 tokens. Model or representation
changes require a new index and regeneration of all document vectors.

OpenSearch retrieves BM25 matches and cosine HNSW neighbors, then its
`score-ranker-processor` combines their ranks using RRF. The application returns
that order unchanged. The title term field has a lexical boost of 3.

`site:`, quoted phrases, and excluded terms/phrases constrain both retrieval
branches before fusion. `site:example.com` matches that host and its subdomains,
not an arbitrary URL substring. Phrase matching uses analyzed terms. A query
needs positive text; operators alone do not enumerate the index.

## Pagination and scores

The native query uses a fixed `pagination_depth` and k-NN `k` of 200. Pages are
slices of this bounded ranking; changing page size does not change fusion depth.
At most 200 results are accessible. API `total` is capped accordingly and is not
a count of all semantically relevant documents on the Web. Index changes can
still change results between requests; this is not a snapshot export API.

`score` is the native RRF score, not a relevance probability. There are no link
rank fields in the projection or public response. The former periodic rank
worker is not part of the serving stack.

## Failure and diagnosis

An embedding or retrieval failure returns HTTP 503, with no lexical fallback.
Check provider availability, the hybrid index schema, and the search pipeline.
For a missing page, check storage, projection exclusions, and text truncation
before changing retrieval. See `search-signals.md` for representation limits.

This implementation follows OpenSearch's published retrieval machinery; it does
not claim a measured quality improvement for this corpus. The integration tests
use deterministic vectors to verify fusion and API behavior, not model quality.

References: [native RRF](https://docs.opensearch.org/2.19/search-plugins/search-pipelines/score-ranker-processor/),
[hybrid pagination](https://docs.opensearch.org/2.19/vector-search/ai-search/hybrid-search/pagination/).
