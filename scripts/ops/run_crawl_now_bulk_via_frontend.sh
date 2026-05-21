#!/usr/bin/env bash
set -euo pipefail

DEFAULT_PRD_SERVER="${WEB_SEARCH_PRD_SERVER:-}"
DEFAULT_PRD_PROJECT="${WEB_SEARCH_PRD_PROJECT:-web-search-prd}"

usage() {
  cat <<'USAGE'
Usage:
  run_crawl_now_bulk_via_frontend.sh prd [url_file]

Examples:
  ./scripts/ops/run_crawl_now_bulk_via_frontend.sh prd urls.txt
  printf '%s\n' https://example.com | ./scripts/ops/run_crawl_now_bulk_via_frontend.sh prd

Notes:
  - Reads one URL per line from a file or stdin.
  - Runs crawl-now inside the frontend container and calls the internal crawler URL.
  - Avoids the public /api/v1/crawl-now rate limit.
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

set_environment_config() {
  case "$ENVIRONMENT" in
    prd)
      require_value WEB_SEARCH_PRD_SERVER "$DEFAULT_PRD_SERVER"
      SERVER="${WEB_SEARCH_SERVER:-$DEFAULT_PRD_SERVER}"
      PROJECT_NAME="$DEFAULT_PRD_PROJECT"
      ;;
    *)
      echo "Unsupported environment: $ENVIRONMENT" >&2
      usage
      exit 1
      ;;
  esac
}

resolve_frontend_container() {
  ssh "$SERVER" bash -s -- "$PROJECT_NAME" <<'REMOTE'
set -euo pipefail

project_name="$1"

docker ps -aq \
  --filter "label=com.docker.compose.project=${project_name}" \
  --filter "label=com.docker.compose.service=frontend" | head -n1
REMOTE
}

run_crawl_now() {
  local url="$1"
  ssh "$SERVER" docker exec -i "$FRONTEND_CONTAINER" python3 - "$url" <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request

url = sys.argv[1]
payload = json.dumps({"url": url}).encode("utf-8")
request = urllib.request.Request(
    os.environ["CRAWLER_SERVICE_URL"].rstrip("/") + "/api/v1/crawl-now",
    data=payload,
    headers={
        "X-API-Key": os.environ["INDEXER_API_KEY"],
        "Content-Type": "application/json",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8")
        status = response.getcode()
except urllib.error.HTTPError as exc:
    body = exc.read().decode("utf-8")
    status = exc.code

print(body)
print(f"HTTP_STATUS:{status}")
PY
}

print_response() {
  local url="$1"
  local response="$2"
  local status body

  status="${response##*$'\n'HTTP_STATUS:}"
  body="${response%$'\n'HTTP_STATUS:*}"
  if [ "$body" = "$response" ]; then
    status=""
  fi

  printf 'URL: %s\n' "$url"
  if [ -n "$status" ]; then
    printf 'http_status: %s\n' "$status"
  fi

  printf '%s' "$body" | python3 -c '
import json
import sys

raw = sys.stdin.read().strip()
if not raw:
    print("empty response")
    raise SystemExit(0)

try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print(raw)
    raise SystemExit(0)

seen = False
for key in ("message", "detail", "indexed_url", "job_id", "status", "error"):
    if key in data:
        print(f"{key}: {data[key]}")
        seen = True
if not seen:
    print(json.dumps(data, ensure_ascii=False))
'
  printf -- '---\n'
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

require_cmd ssh
require_cmd python3

ENVIRONMENT="${1:-}"
if [ -z "$ENVIRONMENT" ]; then
  usage
  exit 1
fi

set_environment_config
URL_FILE="${2:-}"
if [ -n "$URL_FILE" ] && [ ! -f "$URL_FILE" ]; then
  echo "URL file not found: $URL_FILE" >&2
  exit 1
fi

mapfile -t URLS < "${URL_FILE:-/dev/stdin}"

FRONTEND_CONTAINER="$(resolve_frontend_container)"

if [ -z "$FRONTEND_CONTAINER" ]; then
  echo "Could not find frontend container for ${ENVIRONMENT} on ${SERVER}" >&2
  exit 1
fi

echo "Running crawl-now via ${FRONTEND_CONTAINER} on ${SERVER}"

count=0
for url in "${URLS[@]}"; do
  url="$(printf '%s' "$url" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
  [ -z "$url" ] && continue
  response="$(run_crawl_now "$url")"
  print_response "$url" "$response"
  count=$((count + 1))
done

if [ "$count" -eq 0 ]; then
  echo "No URLs provided" >&2
  exit 1
fi
