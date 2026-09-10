# Crawl Priority Scheduling Policy

Merged into `issues/operator-priority-crawl-request.md` on 2026-09-10.

Current queue selection uses age and host eligibility. There is no
`manual_now` profile or per-URL priority bucket in `crawl_queue`.

The need for operator urgency, its effect on ordinary work, and whether it may
bypass any suppression rule remain undecided. Do not infer priority from the
fact that an operator supplied the URL.
