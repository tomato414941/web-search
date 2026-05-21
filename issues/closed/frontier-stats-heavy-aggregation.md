# Frontier Stats Heavy Aggregation

## Problem

Crawler/admin stats still run large `COUNT` and `GROUP BY` queries against
`frontier_entries`.

This conflicts with the read-model direction described in
`docs/architecture.md` and `docs/crawler-concepts.md`: public stats and admin
views should depend on explicit crawler summaries and read models, not rebuild
large state inline.

## Evidence

Production `web-search-prd-postgres-1` was observed near `98%` CPU while
multiple active queries were reading `frontier_entries`.

Observed query shapes included:

```sql
SELECT domain, COUNT(*) as cnt
FROM frontier_entries
WHERE status = 'pending'
GROUP BY domain
ORDER BY cnt DESC, domain ASC;
```

```sql
SELECT status, COUNT(*)
FROM frontier_entries
GROUP BY status;
```

```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'pending' AND next_fetch_at <= ...),
    COUNT(*) FILTER (WHERE status = 'pending' AND next_fetch_at > ...),
    COUNT(*) FILTER (WHERE status = 'leased' ...)
FROM frontier_entries;
```

At the time of observation, `frontier_entries` had roughly 13 million live rows.

Relevant code paths:

- `apps/crawler/src/web_search_crawler/api/routes/stats.py`
- `apps/crawler/src/web_search_crawler/db/url_queries.py`

## Impact

- Admin/stats refresh can become a production database load source.
- Postgres CPU and I/O can rise even when public search traffic is normal.
- The documented read-model architecture is not fully true in production.

## Direction

Move admin and stats endpoints toward persisted summaries such as
`frontier_counters`, `frontier_snapshot`, and `domain_state`.

Avoid request-path or refresh-path recomputation over the full
`frontier_entries` table.

## Investigation Tasks

Before changing queries, map the admin frontier surface:

- List `/admin/frontier` displayed elements.
- Map each element to the frontend read model field.
- Map each field to the crawler API payload field.
- Map each crawler API field to the DB function/query that builds it.
- Mark whether each query reads `frontier_entries`.
- Mark whether each query runs on the request path, refresh path, or background
  path.
- Classify each displayed element as:
  - required for operation
  - useful but can be approximate/stale
  - removable

## Decisions

- Remove `Top Domains in Frontier` from `/admin/frontier`.
  - It is not needed for normal admin operation.
  - Runtime scheduling should use `domain_state`, not a top-domain aggregate
    over `frontier_entries`.
  - If needed for incident investigation, it can be queried manually or via a
    temporary script.
  - Do not keep the `pending_domains` API field for backward compatibility
    without explicit approval.
- Remove `Domain Pressure` from `/admin/frontier`.
  - It is useful only for incident/debug investigation, not normal operation.
  - The display required a domain `GROUP BY` over `frontier_entries` plus a
    `domain_state` join.
  - Domain scheduling truth should remain in `domain_state`; derived pressure
    rankings can be queried manually when needed.
  - Do not keep the `pressure_domains` API field for backward compatibility
    without explicit approval.
- Remove `Top Crawl Profiles` from `/admin/frontier`.
  - It exposes an internal crawl policy distribution rather than an operational
    health signal.
  - The display required `GROUP BY crawl_profile` over `frontier_entries`.
  - If needed for policy debugging, it can be queried manually.
  - Do not keep the `frontier_profile_counts` API field for backward
    compatibility without explicit approval.
- Remove `Ready By Tier` from `/admin/frontier`.
  - It exposes planner-tier distribution rather than a required operator action
    signal.
  - The display required repeated filtered counts over `frontier_entries`.
  - If needed for policy debugging, tier distribution can be queried manually.
  - Do not keep the `frontier_ready_by_tier` API field for backward
    compatibility without explicit approval.
- Remove `Ready Now`, `Scheduled`, and `Expired Leases` from `/admin/frontier`.
  - They are queue timing/debug aggregates, not required operator actions.
  - The display required filtered full-table counts over `frontier_entries`.
  - Expired lease behavior remains visible through frontier maintenance
    `Reclaimed` and `Last Reconcile`.
  - Do not keep the `frontier_ready_counts` API field for backward
    compatibility without explicit approval.
- Stop rebuilding frontier counters from `frontier_entries` during production
  startup and admin stats refresh.
  - Admin refresh should consume the persisted read model instead of creating a
    new full-table count source.
  - Test mode can still force live rebuilds for deterministic integration
    assertions.
- Remove `Inflight Domains`, `Backed Off Domains`, and `Throttled Domains`
  from `/admin/frontier`.
  - `domain_state` remains the crawler's durable host scheduling state.
  - The admin display only exposed aggregate counts, which did not identify
    actionable domains or next operator steps.
  - Do not keep the `domain_state_counts` API field for backward compatibility
    without explicit approval.
- Stop bootstrapping missing `domain_state` rows from the full frontier on
  every crawler startup.
  - `domain_state` remains the durable host scheduling state.
  - New frontier admissions and crawl result updates still create missing
    domain rows locally.
  - Startup still reconciles inflight lease drift, but it no longer scans the
    full frontier to backfill pending-domain rows.
