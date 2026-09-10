# Crawl Frontier Admission Boundary

Closed as a separate boundary issue on 2026-09-10.

Known-URL registration and queue insertion are separate operations in the
current Web model and crawler store. There is no generic `POST /urls` API that
implicitly owns both, and the old `frontier_entries` model is not current.

The remaining question is how admission rules differ for discovered URLs,
operator requests, and recovery. It is tracked in
`issues/frontier-admission-routes-responsibility.md`.
