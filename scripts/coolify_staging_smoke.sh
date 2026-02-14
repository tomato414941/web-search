#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage:
  $(basename "$0") <frontend_url> <indexer_url> <indexer_api_key> [test_url]

Example:
  $(basename "$0") https://stg-search.example.com http://indexer:8000 your-api-key https://example.com
USAGE
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

FRONTEND_URL="${1:-}"
INDEXER_URL="${2:-}"
INDEXER_API_KEY="${3:-}"
TEST_URL="${4:-https://example.com}"

if [ -z "$FRONTEND_URL" ] || [ -z "$INDEXER_URL" ] || [ -z "$INDEXER_API_KEY" ]; then
  usage
  exit 1
fi

trim_slash() {
  local value="$1"
  echo "${value%/}"
}

FRONTEND_URL="$(trim_slash "$FRONTEND_URL")"
INDEXER_URL="$(trim_slash "$INDEXER_URL")"

echo "[1/4] Check frontend health: ${FRONTEND_URL}/health"
health_body="$(curl -fsS "${FRONTEND_URL}/health")"
if ! echo "$health_body" | grep -q '"status"'; then
  echo "Health response is missing status field"
  echo "$health_body"
  exit 1
fi
echo "OK: $health_body"

echo "[2/4] Queue async indexing job"
enqueue_payload=$(cat <<JSON
{"url":"${TEST_URL}","title":"Smoke Test","content":"Smoke test content","outlinks":[]}
JSON
)
enqueue_raw="$(
  curl -sS -w "\n%{http_code}" -X POST "${INDEXER_URL}/api/v1/indexer/page" \
    -H "X-API-Key: ${INDEXER_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "$enqueue_payload"
)"
enqueue_body="$(echo "$enqueue_raw" | sed '$d')"
enqueue_code="$(echo "$enqueue_raw" | tail -n1)"

if [ "$enqueue_code" != "202" ]; then
  echo "Expected 202 from enqueue, got $enqueue_code"
  echo "$enqueue_body"
  exit 1
fi

job_id="$(echo "$enqueue_body" | sed -n 's/.*"job_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
if [ -z "$job_id" ]; then
  echo "job_id not found in enqueue response"
  echo "$enqueue_body"
  exit 1
fi
echo "OK: queued job_id=$job_id"

echo "[3/4] Poll job status"
final_status=""
for _ in $(seq 1 20); do
  status_raw="$(
    curl -sS -w "\n%{http_code}" "${INDEXER_URL}/api/v1/indexer/jobs/${job_id}" \
      -H "X-API-Key: ${INDEXER_API_KEY}"
  )"
  status_body="$(echo "$status_raw" | sed '$d')"
  status_code="$(echo "$status_raw" | tail -n1)"

  if [ "$status_code" != "200" ]; then
    echo "Status API returned $status_code"
    echo "$status_body"
    exit 1
  fi

  current_status="$(echo "$status_body" | sed -n 's/.*"status"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  echo " - status=$current_status"

  if [ "$current_status" = "done" ] || [ "$current_status" = "failed_permanent" ]; then
    final_status="$current_status"
    break
  fi

  sleep 2
done

if [ -z "$final_status" ]; then
  echo "Timed out waiting for final job status"
  exit 1
fi

echo "[4/4] Final result"
if [ "$final_status" = "done" ]; then
  echo "SUCCESS: async indexing completed"
  exit 0
fi

echo "FAILURE: job reached failed_permanent"
exit 2
