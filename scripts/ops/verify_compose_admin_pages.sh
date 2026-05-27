#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DEFAULT_PRD_SERVER="${WEB_SEARCH_PRD_SERVER:-}"
DEFAULT_PRD_ENV_FILE="${WEB_SEARCH_PRD_ENV_FILE:-}"
DEFAULT_PRD_REPO_PATH="${WEB_SEARCH_PRD_REPO_PATH:-}"
DEFAULT_PRD_PROJECT="${WEB_SEARCH_PRD_PROJECT:-web-search-prd}"
DEFAULT_PRD_FRONTEND_URL="${WEB_SEARCH_PRD_FRONTEND_URL:-https://palebluesearch.com}"
DEFAULT_MAX_SECONDS="${VERIFY_ADMIN_MAX_SECONDS:-2.0}"

usage() {
  cat <<'USAGE'
Usage:
  verify_compose_admin_pages.sh prd [max_seconds]

Examples:
  ./scripts/ops/verify_compose_admin_pages.sh prd 2.5

Notes:
  - Measures cold admin page loads after login against compose-managed deployments.
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
      FRONTEND_URL="$DEFAULT_PRD_FRONTEND_URL"
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
    docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "${container}" | sed -n "s/^${key}=//p"
  else
    ssh "$SERVER" \
      "docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' ${container} | sed -n 's/^${key}=//p'"
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

MAX_SECONDS="${2:-$DEFAULT_MAX_SECONDS}"
set_environment_config

if ! is_local_server; then
  require_cmd ssh
fi

FRONTEND_CONTAINER="$(resolve_frontend_container)"
if [ -z "$FRONTEND_CONTAINER" ]; then
  echo "Frontend container not found for ${ENVIRONMENT}" >&2
  exit 1
fi

ADMIN_USERNAME="$(read_container_env "$FRONTEND_CONTAINER" "ADMIN_USERNAME")"
ADMIN_PASSWORD="$(read_container_env "$FRONTEND_CONTAINER" "ADMIN_PASSWORD")"

if [ -z "$ADMIN_USERNAME" ] || [ -z "$ADMIN_PASSWORD" ]; then
  echo "Failed to resolve admin credentials from ${FRONTEND_CONTAINER}" >&2
  exit 1
fi

PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    PYTHON_BIN="$(command -v python)"
  fi
fi

BASE_URL="$FRONTEND_URL" \
ADMIN_USERNAME="$ADMIN_USERNAME" \
ADMIN_PASSWORD="$ADMIN_PASSWORD" \
MAX_SECONDS="$MAX_SECONDS" \
"$PYTHON_BIN" - <<'PY'
import os
import sys
import time

import httpx

base_url = os.environ["BASE_URL"].rstrip("/")
username = os.environ["ADMIN_USERNAME"]
password = os.environ["ADMIN_PASSWORD"]
max_seconds = float(os.environ["MAX_SECONDS"])

checks = [
    ("GET", "/admin/login", 200, {"login": True}),
    ("POST", "/admin/login", 303, {"data": "login"}),
    ("GET", "/admin/", 200, {}),
    ("GET", "/admin/crawlers", 200, {}),
]

failures: list[str] = []

with httpx.Client(
    follow_redirects=False,
    timeout=30.0,
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=0),
) as client:
    for method, path, expected_status, options in checks:
        kwargs: dict[str, object] = {}
        if options.get("data") == "login":
            kwargs["data"] = {
                "username": username,
                "password": password,
                "csrf_token": client.cookies.get("csrf_token"),
            }

        start = time.perf_counter()
        response = client.request(method, base_url + path, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"{method} {path} -> {response.status_code} {elapsed:.4f}s")

        if response.status_code != expected_status:
            failures.append(
                f"{method} {path} returned {response.status_code} (expected {expected_status})"
            )
            continue

        if elapsed > max_seconds:
            failures.append(
                f"{method} {path} took {elapsed:.4f}s (> {max_seconds:.2f}s)"
            )

if failures:
    print("ADMIN VERIFY FAILED")
    for failure in failures:
        print(f"- {failure}")
    sys.exit(1)

print(f"SUCCESS: admin pages loaded within {max_seconds:.2f}s")
PY
