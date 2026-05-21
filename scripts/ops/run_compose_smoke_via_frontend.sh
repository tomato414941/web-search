#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DEFAULT_PRD_SERVER="${WEB_SEARCH_PRD_SERVER:-}"
DEFAULT_PRD_ENV_FILE="${WEB_SEARCH_PRD_ENV_FILE:-}"
DEFAULT_PRD_REPO_PATH="${WEB_SEARCH_PRD_REPO_PATH:-}"
DEFAULT_PRD_PROJECT="${WEB_SEARCH_PRD_PROJECT:-web-search-prd}"
DEFAULT_PRD_FRONTEND_URL="${WEB_SEARCH_PRD_FRONTEND_URL:-https://palebluesearch.com}"
DEFAULT_INDEXER_URL="http://indexer:8000"
DEFAULT_TEST_URL="https://example.com"

usage() {
  cat <<'USAGE'
Usage:
  run_compose_smoke_via_frontend.sh prd [frontend_url] [indexer_url] [test_url]

Examples:
  INDEXER_API_KEY=... ./scripts/ops/run_compose_smoke_via_frontend.sh prd

Notes:
  - Runs the existing smoke script inside the compose-managed frontend container.
  - Uses local INDEXER_API_KEY when set.
  - Otherwise resolves INDEXER_API_KEY from the frontend container env.
USAGE
}

require_cmd() {
  local command="$1"
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required command: $command" >&2
    exit 1
  fi
}

require_value() {
  local name="$1"
  local value="$2"
  if [ -z "$value" ]; then
    echo "Missing required environment variable: $name" >&2
    exit 1
  fi
}

is_local_server() {
  case "$SERVER" in
    local|localhost|127.0.0.1)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

set_environment_config() {
  case "$ENVIRONMENT" in
    prd)
      require_value WEB_SEARCH_PRD_SERVER "$DEFAULT_PRD_SERVER"
      require_value WEB_SEARCH_PRD_ENV_FILE "$DEFAULT_PRD_ENV_FILE"
      require_value WEB_SEARCH_PRD_REPO_PATH "$DEFAULT_PRD_REPO_PATH"
      SERVER="$DEFAULT_PRD_SERVER"
      ENV_FILE="$DEFAULT_PRD_ENV_FILE"
      REPO_PATH="$DEFAULT_PRD_REPO_PATH"
      PROJECT_NAME="$DEFAULT_PRD_PROJECT"
      EXTRA_COMPOSE_FILE="deploy/compose.prd-data.yml"
      DEFAULT_FRONTEND_URL="$DEFAULT_PRD_FRONTEND_URL"
      ;;
    *)
      echo "Unsupported environment: $ENVIRONMENT" >&2
      usage
      exit 1
      ;;
  esac
}

resolve_frontend_container() {
  if is_local_server; then
    bash -s -- "$PROJECT_NAME" <<'REMOTE'
set -euo pipefail

project_name="$1"

docker ps -aq \
  --filter "label=com.docker.compose.project=${project_name}" \
  --filter "label=com.docker.compose.service=frontend" | head -n1
REMOTE
  else
    ssh "$SERVER" bash -s -- "$PROJECT_NAME" <<'REMOTE'
set -euo pipefail

project_name="$1"

docker ps -aq \
  --filter "label=com.docker.compose.project=${project_name}" \
  --filter "label=com.docker.compose.service=frontend" | head -n1
REMOTE
  fi
}

read_container_env() {
  local container="$1"
  local key="$2"
  if is_local_server; then
    docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "${container}" | sed -n "s/^${key}=//p" || true
  else
    ssh "$SERVER" \
      "docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' ${container} | sed -n 's/^${key}=//p'" \
      || true
  fi
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

ENVIRONMENT="${1:-}"
if [ -z "$ENVIRONMENT" ]; then
  usage
  exit 1
fi

set_environment_config

if ! is_local_server; then
  require_cmd ssh
fi

FRONTEND_URL="${2:-$DEFAULT_FRONTEND_URL}"
INDEXER_URL="${3:-$DEFAULT_INDEXER_URL}"
TEST_URL="${4:-$DEFAULT_TEST_URL}"

FRONTEND_CONTAINER="$(resolve_frontend_container)"

if [ -z "$FRONTEND_CONTAINER" ]; then
  echo "Could not find frontend container for ${ENVIRONMENT} on ${SERVER}" >&2
  exit 1
fi

if [ -z "${INDEXER_API_KEY:-}" ]; then
  INDEXER_API_KEY="$(read_container_env "$FRONTEND_CONTAINER" "INDEXER_API_KEY")"
  if [ -z "$INDEXER_API_KEY" ]; then
    echo "Failed to resolve INDEXER_API_KEY from ${FRONTEND_CONTAINER}" >&2
    exit 1
  fi
fi

echo "Running compose smoke inside ${FRONTEND_CONTAINER} on ${SERVER}"
if is_local_server; then
  docker exec -i "$FRONTEND_CONTAINER" bash -s -- \
    "$FRONTEND_URL" \
    "$INDEXER_URL" \
    "$INDEXER_API_KEY" \
    "$TEST_URL" \
    < "$REPO_ROOT/scripts/ops/frontend_smoke.sh"
else
  ssh "$SERVER" \
    docker exec -i "$FRONTEND_CONTAINER" bash -s -- \
    "$FRONTEND_URL" \
    "$INDEXER_URL" \
    "$INDEXER_API_KEY" \
    "$TEST_URL" \
    < "$REPO_ROOT/scripts/ops/frontend_smoke.sh"
fi
