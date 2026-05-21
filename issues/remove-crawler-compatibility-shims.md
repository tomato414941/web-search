# Remove Crawler Compatibility Shims

## Problem

Some crawler code still contains compatibility-oriented behavior or comments
from earlier internal API shapes.

The project should not keep backward-compatible paths by default. Compatibility
should only remain when there is a current caller or an explicit operational
reason.

## Evidence

Observed compatibility references:

- `UrlDiscoveryMixin.record(url, status)` still accepts a `status` argument
  documented as API compatibility.
- `FrontierAdminStateStore.ensure_frontier_snapshot_row()` is documented as a
  compatibility no-op while older call sites are removed.

## Impact

Compatibility shims make the current model harder to read because they preserve
old concepts that may no longer have active callers.

They also make future cleanup harder: new code may copy or depend on behavior
that only exists for historical reasons.

## Direction

Verify current call sites for each compatibility path.

Remove the compatibility behavior if there is no active caller that requires
it. If a caller still exists, update that caller to the current API shape first.

Do not preserve compatibility without explicit approval.
