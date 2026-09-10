# Current retrieval and ranking

This describes the serving implementation, not a requirement that future search
must use the same rules. The product remains general-purpose Web search.
`search-concepts.md` separates that objective from particular retrieval methods.

## Retrieval

`packages/search` prepares the query, retrieves through OpenSearch, and reranks
candidates. Japanese tokenization uses the shared Sudachi analyzer. Operators
include `site:`, quoted phrases, and excluded terms or phrases.

The rule-based classifier selects `navigational`, `reference`, `news`,
`comparison`, or `other`. It consults `config/canonical_sources.json` for known
sources, aliases, preferred paths, candidate windows, and optional restrictions.
A `site:` query bypasses source-policy classification and uses `other`.

Depending on the classification:

- Source matches can boost canonical hosts and preferred paths. A source with
  `restrict_to_source` can filter the candidates to its configured domains.
- A configured `retrieval_query` can replace the positive query terms while
  retaining operators. Check this rewrite when a precise query loses its topic.
- Comparison queries can retrieve using the compared subjects and boost explicit
  comparison wording.
- `news` changes source/path handling. There is no general publication-date or
  freshness ordering, and news classification is not a recency guarantee.

These rules can change which candidates are retrieved, not just their order.
Source fit is a policy heuristic, not a relevance judgment for every query.

## Candidate windows and pagination

The first page can retrieve a larger candidate window before returning the
requested number of hits. Comparison queries use at least 100 candidates;
source-oriented queries use class- and source-dependent windows. Recruiting
page demotion can also expand the window. OpenSearch's candidate limit caps it.

For later pages the engine retrieves only the requested page size at the
corresponding OpenSearch offset, then reranks that page. It does not maintain a
single globally reranked result list across pages. Pages can therefore overlap
or differ from a slice of a globally consistent ranking. Do not treat pagination
as a stable export of the index.

## Reranking

The current Python policy uses ordered sort keys, not a weighted sum of all
signals. Earlier keys take precedence over later keys:

| Class | Ordering after retrieval |
|---|---|
| Navigational, reference, news | Recruiting-page demotion; canonical source fit; title fit; path fit; PageRank; domain rank; original OpenSearch order |
| Comparison | Recruiting-page demotion; comparison fit; title fit; path fit; PageRank; domain rank; original order, followed by domain-diversity promotion |
| Other | Recruiting-page demotion when enabled, then original OpenSearch order |

`score` in the response remains the OpenSearch score. It does not encode these
sort keys. Link ranks are late tie-breakers in selected classes; their presence
in a response does not demonstrate that they improved that result.

## Diagnosing a poor result

1. Check for a degraded API response before interpreting an empty result set.
2. Check whether the page is stored, projected into OpenSearch, and represented
   by searchable text. Content truncation can hide a relevant passage.
3. Check source restrictions, query rewriting, and candidate-window size before
   changing reranking.
4. If the useful page is in the candidate set, inspect the ordering keys and
   comparison diversity behavior.
5. Check whether the evaluation's expectation is appropriate for the query.

`search-signals.md` covers extraction and projection limits.
`search-evaluation.md` explains the limits of the current quality measurements.

## Undecided changes

There is no measured conclusion here that more manual rules, a new weighted
reranker, or vector retrieval should be the next improvement. Compare proposed
methods on controlled inputs and assess quality, latency, and operating cost.
Do not treat the existing source registry or ranking tests as independent proof
of general Web search quality.
