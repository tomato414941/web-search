# Admin Dashboard Surface Simplification

## Problem

The admin dashboard has accumulated operational displays without a clear rule
for whether each item is still worth keeping.

Recent frontier cleanup removed several expensive or low-actionability displays.
The broader admin surface has now been reviewed and narrowed so it does not act
as an ad-hoc analytics UI.

## Evidence

The closed frontier aggregation issue showed that some admin fields were:

- expensive to compute
- not tied to a concrete operator action
- exposed through API contracts only for display
- easier to query manually during incident investigation than to keep as a
  permanent dashboard element

The remaining admin pages are dashboard, crawlers, and indexer views.

## Impact

If admin pages accumulate low-value display fields again, production request
paths and deploy verification can become fragile.

The cost is not only database load. It also includes API contract churn, tests,
frontend complexity, and unclear operator attention.

## Direction

Treat the admin dashboard as an operations summary, not a general analytics
surface.

For future admin additions, classify each displayed element as:

- required for normal operation
- useful but should be stale/approximate/read-model backed
- removable
- incident-only and better served by a manual query or temporary script

Keep fields only when they support a clear operator decision or a deploy-time
health signal.

## Initial Scope

This cleanup covered:

- `/admin/`
- `/admin/crawlers`
- `/admin/indexer`

Avoid broad redesign. The first pass should be an inventory and small removals
where the value is clearly weak.

## Decisions

- Remove `Total Crawled` from `/admin/`.
  - It did not support a clear operator decision beyond existing crawler health
    fields.
  - Crawler status, active tasks, crawl rate, recent errors, and pending
    frontier already cover the normal dashboard decision path.
- Remove `Search Analytics (Today)` from `/admin/`.
  - Search-quality analysis does not belong on the normal operations dashboard.
- Remove `Quick Actions` from `/admin/`.
  - The links duplicated the persistent admin navigation.
  - The dashboard should stay focused on state and attention signals rather
    than acting as a second navigation surface.
- Rename `Recent Errors` to `Errors (1h)` in `/admin/`.
  - The value comes from `error_count_1h`, not from a last-batch counter.
- Remove `/admin/analytics`.
  - Search analytics is a quality-analysis surface, not a normal admin
    operation surface.
  - Search analytics can be revisited as a separate quality workflow when it
    has a clear owner and usage pattern.
- Remove `/admin/seeds`.
  - Seed management remains available through the crawler API and project CLI
    tooling.
  - The admin UI should not keep a permanent production mutation surface for
    editing crawler entry points.
- Remove `/admin/frontier`.
  - The page no longer provided admin actions after earlier frontier cleanup.
  - The remaining fields were primarily read-model internals rather than
    concrete operator decisions.
- Remove `/admin/history`.
  - Crawl history remains available through crawler APIs and stored logs.
  - The admin UI should not keep a permanent log-browser surface without a
    concrete operator action.
- Remove search analytics fields from `/admin/`.
  - `Today's Searches`, `Zero-hit Rate`, and zero-hit query lists are
    search-quality analysis fields rather than normal operations controls.
  - The dashboard should stay focused on crawler/indexer operational state.
