#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SERVER="${WEB_SEARCH_SERVER:-root@5.223.74.201}"
DEFAULT_MAX_SECONDS="${VERIFY_ADMIN_MAX_SECONDS:-2.0}"

usage() {
  cat <<'USAGE'
Usage:
  verify_admin_pages.sh <stg|prd> [max_seconds]

Examples:
  ./scripts/ops/verify_admin_pages.sh stg
  ./scripts/ops/verify_admin_pages.sh prd 2.5

Notes:
  - Measures cold admin page loads after login.
  - Fails when any page exceeds the max allowed seconds.
USAGE
}

require_cmd() {
  local command="$1"
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required command: $command" >&2
    exit 1
  fi
}

set_environment_config() {
  case "$ENVIRONMENT" in
    stg)
      APP_UUID="y0ckcsw84wckcs4g0co8oswo"
      FRONTEND_URL="https://web-search-staging.5.223.74.201.sslip.io"
      ;;
    prd)
      APP_UUID="i8gkcwc00s488g8c4oo84csk"
      FRONTEND_URL="https://palebluesearch.com"
      ;;
    *)
      echo "Unsupported environment: $ENVIRONMENT" >&2
      usage
      exit 1
      ;;
  esac
}

resolve_frontend_container() {
  ssh "$SERVER" \
    "docker ps --format '{{.Names}}' | grep '^frontend-${APP_UUID}-' | head -n1"
}

read_container_env() {
  local container="$1"
  local key="$2"
  ssh "$SERVER" \
    "docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' ${container} | sed -n 's/^${key}=//p'"
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

require_cmd ssh

ENVIRONMENT="${1:-}"
if [ -z "$ENVIRONMENT" ]; then
  usage
  exit 1
fi

MAX_SECONDS="${2:-$DEFAULT_MAX_SECONDS}"
set_environment_config

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
    ("GET", "/admin/indexer", 200, {}),
    ("GET", "/admin/seeds", 200, {}),
    ("GET", "/admin/queue", 200, {}),
]

failures: list[str] = []

with httpx.Client(follow_redirects=False, timeout=30.0) as client:
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
