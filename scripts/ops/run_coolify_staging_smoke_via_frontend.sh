#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DEFAULT_FRONTEND_URL="https://web-search-staging.5.223.74.201.sslip.io"
DEFAULT_INDEXER_URL="http://indexer:8000"
DEFAULT_TEST_URL="https://example.com"
SERVER="${WEB_SEARCH_SERVER:-root@5.223.74.201}"
APP_UUID="${WEB_SEARCH_STG_APP_UUID:-y0ckcsw84wckcs4g0co8oswo}"

usage() {
  cat <<'USAGE'
Usage:
  run_coolify_staging_smoke_via_frontend.sh [frontend_url] [indexer_url] [test_url]

Examples:
  INDEXER_API_KEY=... ./scripts/ops/run_coolify_staging_smoke_via_frontend.sh
  INDEXER_API_KEY=... ./scripts/ops/run_coolify_staging_smoke_via_frontend.sh \
    https://web-search-staging.5.223.74.201.sslip.io \
    http://indexer:8000 \
    https://example.com

Notes:
  - Runs the existing staging smoke script inside the staging frontend container.
  - Uses local INDEXER_API_KEY when set.
  - Otherwise resolves INDEXER_API_KEY from the staging frontend container env.
USAGE
}

require_cmd() {
  local command="$1"
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required command: $command" >&2
    exit 1
  fi
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

require_cmd ssh

resolve_frontend_container() {
  ssh "$SERVER" \
    "docker ps --format '{{.Names}}' | grep '^frontend-${APP_UUID}-' | head -n1" \
    || true
}

read_container_env() {
  local container="$1"
  local key="$2"
  ssh "$SERVER" \
    "docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' ${container} | sed -n 's/^${key}=//p'" \
    || true
}

FRONTEND_URL="${1:-$DEFAULT_FRONTEND_URL}"
INDEXER_URL="${2:-$DEFAULT_INDEXER_URL}"
TEST_URL="${3:-$DEFAULT_TEST_URL}"

FRONTEND_CONTAINER="$(resolve_frontend_container)"

if [ -z "$FRONTEND_CONTAINER" ]; then
  echo "Could not find staging frontend container for app ${APP_UUID} on ${SERVER}" >&2
  exit 1
fi

if [ -z "${INDEXER_API_KEY:-}" ]; then
  INDEXER_API_KEY="$(read_container_env "$FRONTEND_CONTAINER" "INDEXER_API_KEY")"
  if [ -z "$INDEXER_API_KEY" ]; then
    echo "Failed to resolve INDEXER_API_KEY from ${FRONTEND_CONTAINER}" >&2
    exit 1
  fi
fi

echo "Running staging smoke inside ${FRONTEND_CONTAINER} on ${SERVER}"
ssh "$SERVER" \
  docker exec -i "$FRONTEND_CONTAINER" bash -s -- \
  "$FRONTEND_URL" \
  "$INDEXER_URL" \
  "$INDEXER_API_KEY" \
  "$TEST_URL" \
  < "$REPO_ROOT/scripts/ops/coolify_staging_smoke.sh"
