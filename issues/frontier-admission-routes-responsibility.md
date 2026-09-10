# Crawl Queue Admission Policy

## Current behavior

URL registration and queue insertion are separate. The current routes are:

| Route | Effect |
|---|---|
| HTML discovery | Records valid URLs; enqueues at most one eligible same-domain outlink |
| Syndication-feed discovery | Records and requests enqueueing of feed URLs |
| Feed entries | Records URLs without automatically enqueueing them |
| Operator enqueue CLI | Records supplied URLs and requests ordinary queue insertion |
| Link-graph refill CLI | Samples diverse unindexed, unqueued targets and requests insertion |

`CrawlQueueMixin` applies URL admission rules and deduplicates pending URL hashes.
The obsolete `discover_and_admit_urls`, recent-fetch schedule, and recovery-API
paths are not the current implementation.

## Remaining decisions

- Is the current same-domain, one-outlink expansion sufficient for desired
  coverage, alongside graph refill?
- Which eligibility rules should be shared by operator input and automatic
  discovery, and which differences are intentional?
- Should feed entries become crawl candidates, and on what bounded policy?
- If recovery or priority admission is added, what checks may it bypass?

Resolve these as explicit product policies before adding another admission
path. Preserve independent URL registration. Operator urgency is tracked in
`issues/operator-priority-crawl-request.md`; delivery after a queue pop is in
`issues/crawl-queue-delivery-semantics.md`.
