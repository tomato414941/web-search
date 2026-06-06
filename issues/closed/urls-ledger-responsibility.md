# URLs Ledger Responsibility

Closed. The URL ledger no longer stores crawl execution state.

## Problem

`urls` is intended to be the large discovery ledger, but it still stores crawl
execution-derived fields.

The table previously contained discovery identity fields such as `url_hash`,
`url`, `domain`, `created_at`, and `discovered_via`. It also contained
`crawl_count` and `last_crawled_at`, which were updated from crawl execution.

That makes `urls` less simple than a discovery ledger should be.

## Evidence

`record_crawl_result()` updates `urls` on every crawl attempt:

- `last_crawled_at = EXCLUDED.last_crawled_at`
- `crawl_count = urls.crawl_count + 1`

The main observed consumers are management and scheduling-adjacent reads:

- recently crawled suppression before frontier admission
- crawler stats formerly used `done`, `recent`, `uncrawled`, and total URL counts
- seed list status and last-crawled display formerly read crawl state from `urls`
- stale URL helpers and domain crawled-count helpers formerly read crawl state
  from `urls`

Most of these concerns overlap with execution state already present in
`frontier_entries`, such as `last_fetched_at`, `last_success_at`, `last_status`,
`next_fetch_at`, and `fail_streak`.

## Impact

- `urls` can become the largest crawler table because it records every
  discovered URL, including feed entry URLs that are not admitted to the
  frontier.
- Updating `urls` on every crawl attempt increases write pressure on a table
  that should mostly be append/upsert ledger data.
- `crawl_count` and `last_crawled_at` make the boundary between discovery state
  and crawl execution state unclear.
- Admin/stat reads may keep using the largest table when frontier/runtime state
  would be a more natural source.

## Resolution

Keep `urls` focused on URL discovery identity.

Implemented shape:

- `url_hash`
- `url`
- `domain`
- `created_at`

Implemented changes:

- recent-crawl suppression uses `frontier_entries.last_fetched_at`
- crawl result recording no longer updates `urls`
- `urls.crawl_count` and `urls.last_crawled_at` are removed from the schema
- `urls.discovered_via` is removed from the schema
- fresh migrations create `urls` as discovery identity only

Do not move more execution state into `urls` just to reduce table count.
