# Crawler Stats API Responsibility

## Problem

`GET /api/v1/stats` on the crawler service is doing too many jobs.

It currently acts as a shared statistics endpoint for public frontend stats,
admin dashboard data, and crawler instance monitoring. Those callers need
different shapes of information, but they all depend on the same broad response.

This makes weak fields such as `active_seen` hard to remove because they appear
to be part of a shared API contract even when they are not clearly useful for an
operator.

## Evidence

Current crawler stats response includes mixed concerns:

- crawl-attempt metrics such as `crawl_rate_1h`, `attempts_count_1h`, and
  `error_count_1h`
- frontier state such as `frontier_pending` and `leased_tasks`
- URL ledger-derived counts such as `total_seen` and `active_seen`
- snapshot freshness fields such as `frontier_snapshot_age_seconds`
- recent error details for admin display

Frontend callers use different subsets:

- public stats only need frontier pending count and discovered URL count
- admin dashboard needs crawler health, rates, pending work, and recent errors
- crawler instance monitoring combines this endpoint with worker status

## Impact

- The endpoint encourages unrelated display and monitoring concerns to be added
  to one response.
- Fields derived from `urls.last_crawled_at`, especially `active_seen`, keep URL
  execution state alive even if the value is not operationally important.
- Public stats depend on an admin-oriented crawler stats endpoint instead of a
  smaller public summary.
- It is difficult to tell whether removing one field is safe because the API
  has several different consumers.

## Direction

Do not delete the whole endpoint until its active consumers are separated.

Likely cleanup path:

- remove weak fields such as `active_seen` when no concrete UI or operational
  decision depends on them
- keep admin dashboard metrics only if they directly support crawler operation
- split public stats away from admin crawler stats if public stats only need a
  small frontier/index summary
- consider whether crawler instance monitoring should use worker status plus a
  narrower crawler health summary instead of the full stats response
