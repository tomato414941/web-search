# Crawler Stats API Responsibility

## Problem

The crawler stats endpoint was doing too many jobs.

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
- snapshot freshness fields such as `frontier_snapshot_age_seconds`
- recent error details for admin display

Frontend callers use different subsets:

- public stats only need frontier pending count
- admin dashboard needs crawler health, rates, pending work, and recent errors
- crawler instance monitoring combines this endpoint with worker status

## Impact

- The endpoint encourages unrelated display and monitoring concerns to be added
  to one response.
- Public stats depend on an admin-oriented crawler stats endpoint instead of a
  smaller public summary.
- It is difficult to tell whether removing one field is safe because the API
  has several different consumers.

## Direction

Resolved.

- public stats use the crawler frontier summary endpoint
- admin dashboard uses a lightweight dashboard status fetch
- crawler instance monitoring uses separate frontier, crawl-attempt, and worker
  APIs
- the crawler stats endpoint was removed
