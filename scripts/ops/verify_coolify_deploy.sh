#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DEFAULT_TIMEOUT_SEC=240
DEFAULT_POLL_INTERVAL_SEC=5
SERVER="${WEB_SEARCH_SERVER:-root@5.223.74.201}"

usage() {
  cat <<'USAGE'
Usage:
  verify_coolify_deploy.sh <stg|prd> <commit-ish> [timeout_sec]

Examples:
  ./scripts/ops/verify_coolify_deploy.sh stg main
  ./scripts/ops/verify_coolify_deploy.sh prd production 300
  ./scripts/ops/verify_coolify_deploy.sh prd d8ece30

Notes:
  - Coolify deployment status is shown as context only.
  - Success is determined by the actual running containers and public health endpoints.
USAGE
}

require_cmd() {
  local command="$1"
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required command: $command" >&2
    exit 1
  fi
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

load_coolify_auth() {
  if [ -n "${COOLIFY_API_URL:-}" ] && [ -n "${COOLIFY_API_TOKEN:-}" ]; then
    return 0
  fi

  if [ -f "${HOME}/.secrets/coolify" ]; then
    # shellcheck disable=SC1090
    source "${HOME}/.secrets/coolify"
  fi
}

set_environment_config() {
  case "$ENVIRONMENT" in
    stg)
      APP_UUID="y0ckcsw84wckcs4g0co8oswo"
      FRONTEND_URL="https://web-search-staging.5.223.74.201.sslip.io"
      REQUIRED_SERVICES=(
        frontend
        indexer
        indexer-worker
        indexer-maintenance-worker
        postgres
      )
      BUILT_SERVICES=(
        frontend
        indexer
        indexer-worker
        indexer-maintenance-worker
      )
      OPTIONAL_IF_PRESENT_SERVICES=(
        crawler
        opensearch
        prometheus
        grafana
      )
      ;;
    prd)
      APP_UUID="i8gkcwc00s488g8c4oo84csk"
      FRONTEND_URL="https://palebluesearch.com"
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
      BUILT_SERVICES=(
        frontend
        indexer
        indexer-worker
        indexer-maintenance-worker
        crawler
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

  FRONTEND_URL="$(trim_slash "$FRONTEND_URL")"
}

array_contains() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    if [ "$item" = "$needle" ]; then
      return 0
    fi
  done
  return 1
}

get_service_state() {
  local service="$1"

  ssh "$SERVER" bash -s -- "$service" "$APP_UUID" <<'REMOTE'
set -euo pipefail
service="$1"
app_uuid="$2"
container="$(docker ps --format '{{.Names}}' | grep "^${service}-${app_uuid}-" | head -n1 || true)"
if [ -z "$container" ]; then
  exit 0
fi
image="$(docker inspect --format '{{.Config.Image}}' "$container")"
status="$(docker inspect --format '{{.State.Status}}' "$container")"
health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container")"
echo "$container|$image|$status|$health"
REMOTE
}

check_service() {
  local service="$1"
  local require_commit="$2"
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

  if [ "$require_commit" = "yes" ]; then
    if [[ "$image" != *"${EXPECTED_COMMIT}"* ]] && [[ "$image" != *"${EXPECTED_COMMIT_SHORT}"* ]]; then
      echo "wrong-image: ${service} (${container}, image=${image})"
      return 1
    fi
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

latest_deployment_summary() {
  if [ -z "${COOLIFY_API_URL:-}" ] || [ -z "${COOLIFY_API_TOKEN:-}" ]; then
    return 0
  fi

  curl -sS -H "Authorization: Bearer ${COOLIFY_API_TOKEN}" \
    "${COOLIFY_API_URL}/deployments/applications/${APP_UUID}?skip=0&take=1" \
    | jq -r '.deployments[0] | select(.) | "Coolify latest: \(.deployment_uuid) status=\(.status) commit=\(.commit) created_at=\(.created_at) finished_at=\(.finished_at)"'
}

run_checks_once() {
  local failures=0
  local service
  local require_commit
  local readyz_body
  local opensearch_status

  echo "Checking containers on ${SERVER} for ${ENVIRONMENT} (${APP_UUID})"
  if deployment_line="$(latest_deployment_summary)"; then
    if [ -n "$deployment_line" ]; then
      echo "$deployment_line"
    fi
  fi

  for service in "${REQUIRED_SERVICES[@]}"; do
    require_commit="no"
    if array_contains "$service" "${BUILT_SERVICES[@]}"; then
      require_commit="yes"
    fi

    if ! check_service "$service" "$require_commit"; then
      failures=1
    fi
  done

  for service in "${OPTIONAL_IF_PRESENT_SERVICES[@]}"; do
    if state="$(get_service_state "$service")" && [ -n "$state" ]; then
      require_commit="no"
      if array_contains "$service" "${BUILT_SERVICES[@]}"; then
        require_commit="yes"
      fi
      if ! check_service "$service" "$require_commit"; then
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
      if ! check_http_json "${FRONTEND_URL}/api/v1/search?q=test&limit=3" '.total >= 0 and (.mode | type == "string")' >/dev/null; then
        failures=1
      fi
      echo "Checking public stats API"
      if ! check_http_json "${FRONTEND_URL}/api/v1/stats" '.queue and .index' >/dev/null; then
        failures=1
      fi
    else
      echo "Skipping public search/stat checks because opensearch status is ${opensearch_status}"
    fi
  fi

  return "$failures"
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

ENVIRONMENT="${1:-}"
EXPECTED_COMMIT_INPUT="${2:-}"
TIMEOUT_SEC="${3:-$DEFAULT_TIMEOUT_SEC}"

if [ -z "$ENVIRONMENT" ] || [ -z "$EXPECTED_COMMIT_INPUT" ]; then
  usage
  exit 1
fi

require_cmd curl
require_cmd git
require_cmd jq
require_cmd ssh

EXPECTED_COMMIT="$(resolve_commit "$EXPECTED_COMMIT_INPUT")"
EXPECTED_COMMIT_SHORT="${EXPECTED_COMMIT:0:7}"

set_environment_config
load_coolify_auth

echo "Target environment : ${ENVIRONMENT}"
echo "Expected commit    : ${EXPECTED_COMMIT}"
echo "Server             : ${SERVER}"
echo "Frontend URL       : ${FRONTEND_URL}"
echo "Timeout            : ${TIMEOUT_SEC}s"

deadline=$((SECONDS + TIMEOUT_SEC))
attempt=1

while [ "$SECONDS" -lt "$deadline" ]; do
  echo
  echo "Attempt ${attempt}"
  if run_checks_once; then
    echo
    echo "SUCCESS: actual deployment state matches ${EXPECTED_COMMIT_SHORT}"
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
echo "FAILURE: deployment did not converge to ${EXPECTED_COMMIT_SHORT} within ${TIMEOUT_SEC}s"
exit 1
