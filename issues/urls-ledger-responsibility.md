# URLs Ledger Responsibility

## Problem

`urls` is intended to be the large discovery ledger, but it still stores crawl
execution-derived fields.

The table currently contains discovery identity fields such as `url_hash`, `url`,
`domain`, `created_at`, `discovered_via`, and `is_seed`. It also contains
`crawl_count` and `last_crawled_at`, which are updated from crawl execution.

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

## Direction

Keep `urls` focused on URL discovery identity.

Candidate target shape:

- `url_hash`
- `url`
- `domain`
- `created_at`
- `discovered_via`
- `is_seed`

Before removing columns, replace active reads with more appropriate sources:

- use frontier/runtime state for crawl scheduling and recent-crawl suppression
- avoid using `urls` as an admin statistics source
- keep removing remaining `last_crawled_at` and `crawl_count` reads that do not
  belong in the discovery ledger

Do not move more execution state into `urls` just to reduce table count.
