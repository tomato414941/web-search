# Large Local Modules Refactor

## Problem

Some local modules are large enough to make future changes harder to review and
reason about. The observed issue is local module size, not broad monorepo or
package shape.

This should only be handled when one of these modules blocks an active fix or
repeatedly causes confusing changes.

## Evidence

Large modules observed in `apps/`:

- `apps/crawler/src/web_search_crawler/db/url_frontier.py`
- `apps/crawler/src/web_search_crawler/db/url_queries.py`
- `apps/frontend/src/web_search_frontend/services/crawler_admin_client.py`
- `apps/frontend/src/web_search_frontend/services/search_ranking_policy.py`

The import graph did not show direct app-to-app imports or package-to-app
reverse dependencies. `make ci-legacy-paths` also passed.

That suggests the current `apps/` and `packages/` workspace shape is mostly
coherent. The likely cleanup is smaller internal boundaries inside specific
modules.

## Impact

- Larger modules increase review cost.
- Unrelated concerns may become harder to separate.
- Future production fixes may be riskier if they touch broad files with mixed
  responsibilities.

## Direction

Prefer targeted module splits only when they support an active fix. Do not
split these files just to reduce line counts.

Potential future cuts:

- split expensive crawler stats/admin queries out of `url_queries.py`
- split frontier lease selection/completion helpers in `url_frontier.py`
- split crawler admin cache/read-model/fetching concerns in
  `crawler_admin_client.py`
- keep ranking policy changes evaluation-driven before splitting
  `search_ranking_policy.py`

Avoid broad package reshaping unless concrete cross-package dependency problems
appear.
