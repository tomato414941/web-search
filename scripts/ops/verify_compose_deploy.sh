#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DEFAULT_TIMEOUT_SEC=240
DEFAULT_POLL_INTERVAL_SEC=5
DEFAULT_PRD_SERVER="${WEB_SEARCH_PRD_SERVER:-}"
DEFAULT_PRD_ENV_FILE="${WEB_SEARCH_PRD_ENV_FILE:-}"
DEFAULT_PRD_REPO_PATH="${WEB_SEARCH_PRD_REPO_PATH:-}"
DEFAULT_PRD_PROJECT="${WEB_SEARCH_PRD_PROJECT:-web-search-prd}"
DEFAULT_PRD_FRONTEND_URL="${WEB_SEARCH_PRD_FRONTEND_URL:-https://palebluesearch.com}"
DEFAULT_PRD_OPENSEARCH_DATA_DIR="${WEB_SEARCH_PRD_OPENSEARCH_DATA_DIR:-/var/lib/web-search/opensearch-data}"

usage() {
  cat <<'USAGE'
Usage:
  verify_compose_deploy.sh prd <git-ref> [timeout_sec]

Examples:
  ./scripts/ops/verify_compose_deploy.sh prd main 300

Notes:
  - Success is determined by the deployed state file, running compose services,
    and public health endpoints.
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

trim_slash() {
  local value="$1"
  echo "${value%/}"
}

resolve_commit() {
  local ref="$1"
  if git -C "$REPO_ROOT" rev-parse --verify "${ref}^{commit}" >/dev/null 2>&1; then
    git -C "$REPO_ROOT" rev-parse "${ref}^{commit}"
  else
    echo "$ref"
  fi
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
      STATE_FILE="${REPO_PATH}/.deploy-state/prd.env"
      EXTRA_COMPOSE_FILE="deploy/compose.prd-data.yml"
      FRONTEND_URL="$DEFAULT_PRD_FRONTEND_URL"
      OPENSEARCH_DATA_DIR="$DEFAULT_PRD_OPENSEARCH_DATA_DIR"
      REQUIRED_SERVICES=(
        frontend
        indexer
        indexer-worker
        indexer-maintenance-worker
        crawler
        postgres
        opensearch
        prometheus
        grafana
      )
      OPTIONAL_IF_PRESENT_SERVICES=()
      ;;
    *)
      echo "Unsupported environment: $ENVIRONMENT" >&2
      usage
      exit 1
      ;;
  esac

  if is_local_server; then
    REPO_PATH="$REPO_ROOT"
  fi

  FRONTEND_URL="$(trim_slash "$FRONTEND_URL")"
}

read_state_value() {
  local key="$1"

  if is_local_server; then
    if [ ! -f "$STATE_FILE" ]; then
      return 0
    fi
    sed -n "s/^${key}=//p" "$STATE_FILE" | head -n1
  else
    ssh "$SERVER" "if [ -f '$STATE_FILE' ]; then sed -n 's/^${key}=//p' '$STATE_FILE' | head -n1; fi"
  fi
}

get_fallback_remote_head() {
  if is_local_server; then
    if [ ! -d "$REPO_PATH/.git" ]; then
      exit 0
    fi
    git config --global --add safe.directory "$REPO_PATH" >/dev/null 2>&1 || true
    (cd "$REPO_PATH" && git rev-parse HEAD)
  else
    ssh "$SERVER" "if [ -d '$REPO_PATH/.git' ]; then cd '$REPO_PATH' && git rev-parse HEAD; fi"
  fi
}

get_deployed_commit() {
  local deployed_commit

  deployed_commit="$(read_state_value "DEPLOY_COMMIT")"
  if [ -n "$deployed_commit" ]; then
    echo "$deployed_commit"
    return 0
  fi

  get_fallback_remote_head
}

get_service_state() {
  local service="$1"

  if is_local_server; then
    bash -s -- "$PROJECT_NAME" "$service" <<'REMOTE'
set -euo pipefail

project_name="$1"
service="$2"

container_id="$(docker ps -aq \
  --filter "label=com.docker.compose.project=${project_name}" \
  --filter "label=com.docker.compose.service=${service}" | head -n1)"
if [ -z "$container_id" ]; then
  exit 0
fi

name="$(docker inspect --format '{{.Name}}' "$container_id" | sed 's#^/##')"
image="$(docker inspect --format '{{.Config.Image}}' "$container_id")"
status="$(docker inspect --format '{{.State.Status}}' "$container_id")"
health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")"
echo "$name|$image|$status|$health"
REMOTE
  else
    ssh "$SERVER" bash -s -- "$PROJECT_NAME" "$service" <<'REMOTE'
set -euo pipefail

project_name="$1"
service="$2"

container_id="$(docker ps -aq \
  --filter "label=com.docker.compose.project=${project_name}" \
  --filter "label=com.docker.compose.service=${service}" | head -n1)"
if [ -z "$container_id" ]; then
  exit 0
fi

name="$(docker inspect --format '{{.Name}}' "$container_id" | sed 's#^/##')"
image="$(docker inspect --format '{{.Config.Image}}' "$container_id")"
status="$(docker inspect --format '{{.State.Status}}' "$container_id")"
health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")"
echo "$name|$image|$status|$health"
REMOTE
  fi
}

check_service() {
  local service="$1"
  local state
  local container
  local image
  local status
  local health

  state="$(get_service_state "$service")"
  if [ -z "$state" ]; then
    echo "missing: ${service}"
    return 1
  fi

  IFS='|' read -r container image status health <<<"$state"

  if [ "$status" != "running" ]; then
    echo "not-running: ${service} (${container}, status=${status})"
    return 1
  fi

  if [ "$health" != "healthy" ] && [ "$health" != "none" ]; then
    echo "not-healthy: ${service} (${container}, health=${health})"
    return 1
  fi

  echo "ok: ${service} (${container}, image=${image}, health=${health})"
}

check_http_json() {
  local url="$1"
  local jq_filter="$2"
  local body
  local code
  local raw

  raw="$(curl -sS -w '\n%{http_code}' "$url")"
  body="$(echo "$raw" | sed '$d')"
  code="$(echo "$raw" | tail -n1)"

  if [ "$code" != "200" ]; then
    echo "HTTP ${code} from ${url}"
    echo "$body"
    return 1
  fi

  if ! echo "$body" | jq -e "$jq_filter" >/dev/null; then
    echo "Unexpected JSON from ${url}"
    echo "$body"
    return 1
  fi

  echo "$body"
}

run_checks_once() {
  local failures=0
  local service
  local readyz_body
  local opensearch_status
  local deployed_commit

  deployed_commit="$(get_deployed_commit)"
  echo "Deployed commit    : ${deployed_commit:-unknown}"
  if [ -z "$deployed_commit" ] || [ "$deployed_commit" != "$EXPECTED_COMMIT" ]; then
    echo "wrong-head: expected ${EXPECTED_COMMIT}"
    failures=1
  fi

  echo "Checking compose services on ${SERVER} for ${ENVIRONMENT} (${PROJECT_NAME})"
  for service in "${REQUIRED_SERVICES[@]}"; do
    if ! check_service "$service"; then
      failures=1
    fi
  done

  for service in "${OPTIONAL_IF_PRESENT_SERVICES[@]}"; do
    if state="$(get_service_state "$service")" && [ -n "$state" ]; then
      if ! check_service "$service"; then
        failures=1
      fi
    fi
  done

  echo "Checking public health: ${FRONTEND_URL}/health"
  if ! check_http_json "${FRONTEND_URL}/health" '.status == "ok"' >/dev/null; then
    failures=1
  fi

  echo "Checking readiness: ${FRONTEND_URL}/readyz"
  if ! readyz_body="$(check_http_json "${FRONTEND_URL}/readyz" '.status == "ok"')"; then
    failures=1
  else
    opensearch_status="$(echo "$readyz_body" | jq -r '.checks.opensearch.status // .checks.opensearch // "unknown"')"
    if [ "$opensearch_status" = "ok" ]; then
      echo "Checking public search API"
      if ! check_http_json "${FRONTEND_URL}/api/v1/search?q=test&limit=3" '.total >= 0 and (.mode | type == "string") and (.degraded != true) and (.error_type == null)' >/dev/null; then
        failures=1
      fi
      echo "Checking public stats API"
      if ! check_http_json "${FRONTEND_URL}/api/v1/stats" '.frontier and .index' >/dev/null; then
        failures=1
      fi
    else
      echo "Skipping public search/stat checks because opensearch status is ${opensearch_status}"
    fi
  fi

  return "$failures"
}

build_success_message() {
  echo "SUCCESS: deployed commit matches ${EXPECTED_COMMIT_SHORT}"
}

build_failure_message() {
  echo "FAILURE: deployment did not converge to deployed commit ${EXPECTED_COMMIT_SHORT} within ${TIMEOUT_SEC}s"
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

ENVIRONMENT="${1:-}"
EXPECTED_REF_INPUT="${2:-}"
TIMEOUT_SEC="${3:-$DEFAULT_TIMEOUT_SEC}"

if [ -z "$ENVIRONMENT" ] || [ -z "$EXPECTED_REF_INPUT" ]; then
  usage
  exit 1
fi

require_cmd curl
require_cmd git
require_cmd jq

EXPECTED_COMMIT="$(resolve_commit "$EXPECTED_REF_INPUT")"
EXPECTED_COMMIT_SHORT="${EXPECTED_COMMIT:0:7}"

set_environment_config

if ! is_local_server; then
  require_cmd ssh
fi

echo "Target environment : ${ENVIRONMENT}"
echo "Expected git ref   : ${EXPECTED_REF_INPUT}"
echo "Expected commit    : ${EXPECTED_COMMIT}"
echo "Server             : ${SERVER}"
echo "Repo path          : ${REPO_PATH}"
echo "State file         : ${STATE_FILE}"
echo "Compose project    : ${PROJECT_NAME}"
echo "Frontend URL       : ${FRONTEND_URL}"
echo "Timeout            : ${TIMEOUT_SEC}s"

deadline=$((SECONDS + TIMEOUT_SEC))
attempt=1

while [ "$SECONDS" -lt "$deadline" ]; do
  echo
  echo "Attempt ${attempt}"
  if run_checks_once; then
    echo
    build_success_message
    exit 0
  fi

  if [ "$SECONDS" -ge "$deadline" ]; then
    break
  fi

  echo "Waiting ${DEFAULT_POLL_INTERVAL_SEC}s before retry..."
  sleep "$DEFAULT_POLL_INTERVAL_SEC"
  attempt=$((attempt + 1))
done

echo
build_failure_message
exit 1
