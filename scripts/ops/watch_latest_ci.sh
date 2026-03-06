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
  - If the ref resolves to a local branch, only runs for that branch are considered.
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

resolve_branch() {
  local ref="$1"

  if [ "$ref" = "HEAD" ]; then
    git -C "$REPO_ROOT" symbolic-ref --quiet --short HEAD || true
    return 0
  fi

  if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/${ref}"; then
    echo "$ref"
    return 0
  fi

  if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/remotes/origin/${ref}"; then
    echo "$ref"
    return 0
  fi
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
TARGET_BRANCH="$(resolve_branch "$TARGET_REF")"
REPO="$(resolve_repo)"
WAIT_TIMEOUT_SEC="${WATCH_CI_TIMEOUT_SEC:-60}"
POLL_INTERVAL_SEC="${WATCH_CI_POLL_INTERVAL_SEC:-3}"
deadline=$((SECONDS + WAIT_TIMEOUT_SEC))
run_id=""

while [ "$SECONDS" -lt "$deadline" ]; do
  if [ -n "$TARGET_BRANCH" ]; then
    run_id="$(
      gh run list \
        --repo "$REPO" \
        --branch "$TARGET_BRANCH" \
        --event push \
        --limit 20 \
        --json databaseId,headSha,createdAt \
        | jq -r --arg sha "$TARGET_SHA" '
            map(select(.headSha == $sha))
            | sort_by(.createdAt)
            | last
            | .databaseId // empty
          '
    )"
  else
    run_id="$(
      gh run list \
        --repo "$REPO" \
        --event push \
        --limit 20 \
        --json databaseId,headSha,createdAt \
        | jq -r --arg sha "$TARGET_SHA" '
            map(select(.headSha == $sha))
            | sort_by(.createdAt)
            | last
            | .databaseId // empty
          '
    )"
  fi

  if [ -n "$run_id" ]; then
    break
  fi

  sleep "$POLL_INTERVAL_SEC"
done

if [ -z "$run_id" ]; then
  if [ -n "$TARGET_BRANCH" ]; then
    echo "No push-triggered GitHub Actions run found for ${TARGET_BRANCH} at ${TARGET_SHA}" >&2
  else
    echo "No push-triggered GitHub Actions run found for commit ${TARGET_SHA}" >&2
  fi
  exit 1
fi

if [ -n "$TARGET_BRANCH" ]; then
  echo "Watching CI run ${run_id} for ${TARGET_BRANCH} (${TARGET_SHA})"
else
  echo "Watching CI run ${run_id} for ${TARGET_SHA}"
fi
gh run watch "$run_id" --repo "$REPO" --exit-status
