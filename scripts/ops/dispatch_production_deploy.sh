#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

WORKFLOW_NAME="${WEB_SEARCH_PRODUCTION_DEPLOY_WORKFLOW:-Production Deploy}"
LOOKUP_TIMEOUT_SEC="${WEB_SEARCH_DISPATCH_LOOKUP_TIMEOUT_SEC:-60}"
POLL_INTERVAL_SEC="${WEB_SEARCH_DISPATCH_POLL_INTERVAL_SEC:-3}"
SUCCESS_WINDOW_SEC="${WEB_SEARCH_PRODUCTION_DEPLOY_SUCCESS_WINDOW_SEC:-3600}"
ALLOW_REDEPLOY="${WEB_SEARCH_ALLOW_PRODUCTION_REDEPLOY:-0}"
DRY_RUN=0

usage() {
  cat <<'USAGE'
Usage:
  dispatch_production_deploy.sh [--dry-run] <git_ref>

Examples:
  ./scripts/ops/dispatch_production_deploy.sh main
  ./scripts/ops/dispatch_production_deploy.sh --dry-run 0123abcd

Notes:
  - This is the normal production deploy entrypoint.
  - It dispatches the GitHub Actions "Production Deploy" workflow.
  - If GitHub returns an HTTP 500 after accepting the dispatch, this script
    searches for the created run before retrying.
  - Direct compose deployment is reserved for explicit emergency fallback.
USAGE
}

require_cmd() {
  local command="$1"
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required command: $command" >&2
    exit 1
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

resolve_dispatch_commit() {
  local ref="$1"
  local sha

  if sha="$(gh api "repos/${REPO}/commits/${ref}" --jq '.sha' 2>/dev/null)"; then
    if [ -n "$sha" ]; then
      echo "$sha"
      return 0
    fi
  fi

  git -C "$REPO_ROOT" rev-parse --verify "${ref}^{commit}"
}

active_production_run() {
  gh run list \
    --repo "$REPO" \
    --workflow "$WORKFLOW_NAME" \
    --event workflow_dispatch \
    --limit 20 \
    --json databaseId,createdAt,headSha,status,url \
    | jq -r '
        map(select(.status != "completed"))
        | sort_by(.createdAt)
        | last
        | if . then [.databaseId, .status, .headSha, .createdAt, .url] | @tsv else empty end
      '
}

recent_successful_target_run() {
  local now_epoch="$1"

  gh run list \
    --repo "$REPO" \
    --workflow "$WORKFLOW_NAME" \
    --event workflow_dispatch \
    --limit 20 \
    --json databaseId,createdAt,conclusion,headSha,status,url \
    | jq -r \
      --arg sha "$TARGET_SHA" \
      --argjson now "$now_epoch" \
      --argjson window "$SUCCESS_WINDOW_SEC" '
        map(select(
          .status == "completed"
          and .conclusion == "success"
          and .headSha == $sha
        ))
        | map(. + {epoch: (.createdAt | fromdateiso8601)})
        | map(select(($now - .epoch) <= $window))
        | sort_by(.epoch)
        | last
        | if . then [.databaseId, .createdAt, .url] | @tsv else empty end
      '
}

find_dispatched_run() {
  local start_epoch="$1"

  gh run list \
    --repo "$REPO" \
    --workflow "$WORKFLOW_NAME" \
    --event workflow_dispatch \
    --limit 20 \
    --json databaseId,createdAt,conclusion,headSha,status,url \
    | jq -r \
      --arg sha "$TARGET_SHA" \
      --argjson start "$start_epoch" '
        map(select(.headSha == $sha))
        | map(. + {epoch: (.createdAt | fromdateiso8601)})
        | map(select(.epoch >= ($start - 5)))
        | sort_by(.epoch)
        | last
        | if . then [.databaseId, .status, (.conclusion // ""), .createdAt, .url] | @tsv else empty end
      '
}

poll_for_dispatched_run() {
  local start_epoch="$1"
  local deadline=$((SECONDS + LOOKUP_TIMEOUT_SEC))
  local run=""

  while [ "$SECONDS" -lt "$deadline" ]; do
    run="$(find_dispatched_run "$start_epoch")"
    if [ -n "$run" ]; then
      echo "$run"
      return 0
    fi
    sleep "$POLL_INTERVAL_SEC"
  done

  return 1
}

dispatch_once() {
  local output_file="$1"
  gh workflow run "$WORKFLOW_NAME" \
    --repo "$REPO" \
    -f git_ref="$TARGET_REF" \
    >"$output_file" 2>&1
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
  shift
fi

TARGET_REF="${1:-}"
if [ -z "$TARGET_REF" ]; then
  usage
  exit 1
fi

require_cmd date
require_cmd gh
require_cmd git
require_cmd jq

REPO="$(resolve_repo)"
TARGET_SHA="$(resolve_dispatch_commit "$TARGET_REF")"
now_epoch="$(date -u +%s)"

echo "Workflow        : ${WORKFLOW_NAME}"
echo "Repository      : ${REPO}"
echo "Git ref         : ${TARGET_REF}"
echo "Resolved commit : ${TARGET_SHA}"

active_run="$(active_production_run)"
if [ -n "$active_run" ]; then
  IFS=$'\t' read -r run_id run_status run_sha run_created run_url <<<"$active_run"
  echo "Production deploy is already ${run_status}: ${run_id} (${run_sha}, ${run_created})" >&2
  echo "$run_url" >&2
  exit 1
fi

if [ "$ALLOW_REDEPLOY" != "1" ]; then
  recent_success="$(recent_successful_target_run "$now_epoch")"
  if [ -n "$recent_success" ]; then
    IFS=$'\t' read -r run_id run_created run_url <<<"$recent_success"
    echo "Production deploy for this commit already succeeded recently: ${run_id} (${run_created})"
    echo "$run_url"
    echo "Set WEB_SEARCH_ALLOW_PRODUCTION_REDEPLOY=1 to intentionally redeploy the same commit."
    exit 0
  fi
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "Dry run only. No workflow dispatch was sent."
  exit 0
fi

dispatch_output="$(mktemp)"
trap 'rm -f "$dispatch_output"' EXIT

attempt_start_epoch="$(date -u +%s)"
echo "Dispatching production deploy..."
if dispatch_once "$dispatch_output"; then
  cat "$dispatch_output"
  dispatch_status=0
else
  dispatch_status=$?
  cat "$dispatch_output" >&2
fi

if run="$(poll_for_dispatched_run "$attempt_start_epoch")"; then
  IFS=$'\t' read -r run_id run_status _run_conclusion run_created run_url <<<"$run"
  if [ "$dispatch_status" -ne 0 ]; then
    echo "Dispatch returned a non-zero status, but a workflow run was created: ${run_id} (${run_status}, ${run_created})"
  else
    echo "Workflow run created: ${run_id} (${run_status}, ${run_created})"
  fi
  echo "$run_url"
  gh run watch "$run_id" --repo "$REPO" --exit-status
  exit $?
fi

if [ "$dispatch_status" -ne 0 ]; then
  echo "No workflow run appeared after the failed dispatch. Retrying once..." >&2
  : >"$dispatch_output"
  attempt_start_epoch="$(date -u +%s)"
  if dispatch_once "$dispatch_output"; then
    cat "$dispatch_output"
    dispatch_status=0
  else
    dispatch_status=$?
    cat "$dispatch_output" >&2
  fi

  if run="$(poll_for_dispatched_run "$attempt_start_epoch")"; then
    IFS=$'\t' read -r run_id run_status _run_conclusion run_created run_url <<<"$run"
    echo "Workflow run created after retry: ${run_id} (${run_status}, ${run_created})"
    echo "$run_url"
    gh run watch "$run_id" --repo "$REPO" --exit-status
    exit $?
  fi
fi

echo "Failed to create or find a Production Deploy workflow run." >&2
echo "Do not run direct production compose deploy unless this is an explicit emergency fallback." >&2
exit 1
