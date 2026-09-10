# Crawl Queue Delivery and Recovery

## Observed behavior

`CrawlQueueMixin.pop_ready_crawl_tasks()` selects pending rows with transaction
locks and deletes them before returning tasks to the worker. In-progress work
is tracked only in memory. The worker cancels outstanding tasks on shutdown.

Failure handling records attempt logs and domain state without requeueing the
URL. A crash, cancellation, or timeout after a pop can therefore leave no
pending attempt. A later rediscovery, operator enqueue, or graph refill may add
the URL again, but this is not an at-least-once delivery guarantee.

## Decision needed

Decide whether this loss behavior is acceptable for the current crawl objective.
If it is, keep the limitation explicit for operators. If recovery is required,
define the guarantee before choosing retry, lease, or acknowledgment machinery.

Verification should cover shutdown after pop, failure before/after indexer
commit, duplicate admission during an active fetch, and the expected recovery
path. This issue records a behavior found during documentation review; the
required delivery guarantee is not yet decided.
