# Known URL Registration Boundary

Closed after implementation review on 2026-09-10.

`UrlLedgerRepository` in `packages/web-model` records known URLs independently
of crawl work. Its write stores URL identity and creation time, not scheduling
state. Operator enqueue and frontier refill call registration and queue
insertion separately.

The original concern was that registering a URL implicitly scheduled a fetch.
Preserve the current separation. Admission and operator-priority questions are
tracked in `issues/frontier-admission-routes-responsibility.md` and
`issues/operator-priority-crawl-request.md`.
