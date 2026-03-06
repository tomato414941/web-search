#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

usage() {
  cat <<'USAGE'
Usage:
  watch_latest_ci.sh [commit-ish]

Examples:
  ./scripts/ops/watch_latest_ci.sh
  ./scripts/ops/watch_latest_ci.sh main
  ./scripts/ops/watch_latest_ci.sh production

Notes:
  - Watches the latest push-triggered GitHub Actions run for the resolved commit.
  - Defaults to the current HEAD commit.
USAGE
}

require_cmd() {
  local command="$1"
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required command: $command" >&2
    exit 1
  fi
}

resolve_commit() {
  local ref="$1"
  git -C "$REPO_ROOT" rev-parse --verify "${ref}^{commit}"
}

resolve_repo() {
  local repo
  if repo="$(gh repo view --json nameWithOwner -q '.nameWithOwner' 2>/dev/null)"; then
    if [ -n "$repo" ]; then
      echo "$repo"
      return 0
    fi
  fi

  repo="$(git -C "$REPO_ROOT" remote get-url origin)"
  repo="${repo#git@github.com:}"
  repo="${repo#https://github.com/}"
  repo="${repo%.git}"
  echo "$repo"
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

require_cmd gh
require_cmd git
require_cmd jq

TARGET_REF="${1:-HEAD}"
TARGET_SHA="$(resolve_commit "$TARGET_REF")"
REPO="$(resolve_repo)"

run_id="$(
  gh run list \
    --repo "$REPO" \
    --limit 20 \
    --json databaseId,headSha,event,createdAt,displayTitle \
    | jq -r --arg sha "$TARGET_SHA" '
        map(select(.headSha == $sha and .event == "push"))
        | sort_by(.createdAt)
        | last
        | .databaseId // empty
      '
)"

if [ -z "$run_id" ]; then
  echo "No push-triggered GitHub Actions run found for commit ${TARGET_SHA}" >&2
  exit 1
fi

echo "Watching CI run ${run_id} for ${TARGET_SHA}"
gh run watch "$run_id" --repo "$REPO" --exit-status
