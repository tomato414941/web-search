# Observed Web Model Semantics

## Implemented ownership

`packages/web-model` owns known URLs, observed links, referring-host observations,
and graph-derived rank storage/calculation. The crawler observes pages and writes
through these repositories; the indexer writes documents, not the link graph.

`process_html_result()` replaces observed links before submitting page text to
the indexer. Thus an edge's source is a parsed URL, not necessarily a successfully
indexed document. Destinations can be unindexed URLs.

## Remaining decisions

- `links` replaces a source's edges on each observation, while
  `url_referring_hosts` upserts historical host observations without deleting
  missing ones. What retention/freshness should consumers assume?
- Should feed-entry relations remain implicit or become a distinct graph relation
  when a concrete consumer needs that distinction?
- Should link-rank computation use all observed nodes or only indexed documents?
  Decide alongside its memory cost and search use in
  `issues/link-authority-signal-design.md`.

Physical uniqueness/index repair is historical work recorded in
`issues/closed/links-physical-schema-drift.md`. Do not treat the old schema drift
as an unresolved ownership move without new evidence.
