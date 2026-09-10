# URL Registry Ownership

Closed after implementation review on 2026-09-10.

Known URL persistence now belongs to `packages/web-model` through
`UrlLedgerRepository`; crawler runtime state belongs to `crawl_queue` and
`domain_state`. The original claim that URL persistence was implemented inside
the crawler store is obsolete.

This resolves storage ownership, not every future URL-source policy. Questions
about observed graph semantics remain in `issues/web-model-boundary.md`.
