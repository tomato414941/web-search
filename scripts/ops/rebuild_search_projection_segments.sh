#!/usr/bin/env bash
set -euo pipefail

DEFAULT_PRD_SERVER="${WEB_SEARCH_PRD_SERVER:-}"
DEFAULT_PRD_PROJECT="${WEB_SEARCH_PRD_PROJECT:-web-search-prd}"
DEFAULT_PRD_FRONTEND_URL="${WEB_SEARCH_PRD_FRONTEND_URL:-https://palebluesearch.com}"
DEFAULT_PRD_STATE_FILE="${WEB_SEARCH_PRD_REBUILD_STATE_FILE:-/srv/web-search/.maintenance/search-projection-rebuild.env}"
DEFAULT_BATCH_SIZE=100
DEFAULT_SEGMENT_SIZE=10000
DEFAULT_OPENSEARCH_URL="http://opensearch:9200"

usage() {
  cat <<'USAGE'
Usage:
  rebuild_search_projection_segments.sh prd [options]

Options:
  --batch-size N         Rebuild CLI batch size. Default: 100.
  --segment-size N       Documents per segment. Default: 10000.
  --max-segments N       Stop after N segments. Omit to continue until exhausted.
  --start-after-url URL  Override saved state and start after this URL.
  --state-file PATH      Remote state file. Default: /srv/web-search/.maintenance/search-projection-rebuild.env.
  --opensearch-url URL   OpenSearch URL inside the indexer container. Default: http://opensearch:9200.
  --index-name NAME      OpenSearch index or alias name to rebuild.

Environment:
  WEB_SEARCH_PRD_SERVER  Required for prd, for example root@5.223.74.201.

Notes:
  - Saves LAST_URL after each successful segment.
  - Runs OpenSearch health and public search checks after each segment.
  - If a segment fails after logging last_url, the state file is still advanced
    to the last processed URL before the script exits nonzero.
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

base64_encode() {
  if [ -z "$1" ]; then
    echo "__EMPTY__"
  else
    printf '%s' "$1" | base64 | tr -d '\n'
  fi
}

read_state_value() {
  local key="$1"
  ssh "$SERVER" bash -s -- "$STATE_FILE" "$key" <<'REMOTE'
set -euo pipefail
state_file="$1"
key="$2"
if [ -f "$state_file" ]; then
  sed -n "s/^${key}=//p" "$state_file" | tail -n1
fi
REMOTE
}

write_state() {
  local last_url="$1"
  local segments_completed="$2"
  local last_status="$3"
  local updated_at
  local last_url_b64
  updated_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  last_url_b64="$(base64_encode "$last_url")"

  ssh "$SERVER" bash -s -- \
    "$STATE_FILE" \
    "$last_url_b64" \
    "$segments_completed" \
    "$last_status" \
    "$updated_at" <<'REMOTE'
set -euo pipefail
state_file="$1"
if [ "$2" = "__EMPTY__" ]; then
  last_url=""
else
  last_url="$(printf '%s' "$2" | base64 -d)"
fi
segments_completed="$3"
last_status="$4"
updated_at="$5"
mkdir -p "$(dirname "$state_file")"
cat > "$state_file" <<STATE
LAST_URL=${last_url}
SEGMENTS_COMPLETED=${segments_completed}
LAST_STATUS=${last_status}
UPDATED_AT=${updated_at}
STATE
REMOTE
}

run_segment() {
  local start_after_url="$1"
  local output_file="$2"
  local start_after_url_b64
  local status
  start_after_url_b64="$(base64_encode "$start_after_url")"

  set +e
  ssh "$SERVER" bash -s -- \
    "$PROJECT_NAME" \
    "$BATCH_SIZE" \
    "$SEGMENT_SIZE" \
    "$start_after_url_b64" \
    "$OPENSEARCH_URL" \
    "$INDEX_NAME" <<'REMOTE' 2>&1 | tee "$output_file"
set -euo pipefail
project_name="$1"
batch_size="$2"
segment_size="$3"
if [ "$4" = "__EMPTY__" ]; then
  start_after_url=""
else
  start_after_url="$(printf '%s' "$4" | base64 -d)"
fi
opensearch_url="$5"
index_name="$6"

container_id="$(docker ps -q \
  --filter "label=com.docker.compose.project=${project_name}" \
  --filter "label=com.docker.compose.service=indexer" | head -n1)"
if [ -z "$container_id" ]; then
  echo "Missing running indexer container for project ${project_name}" >&2
  exit 1
fi

cmd=(
  web-search-rebuild-search-projection
  --batch-size "$batch_size"
  --max-documents "$segment_size"
  --opensearch-url "$opensearch_url"
)
if [ -n "$index_name" ]; then
  cmd+=(--index-name "$index_name")
fi
if [ -n "$start_after_url" ]; then
  cmd+=(--start-after-url "$start_after_url")
fi

docker exec "$container_id" "${cmd[@]}"
REMOTE
  status=${PIPESTATUS[0]}
  set -e
  return "$status"
}

extract_last_url() {
  local output_file="$1"
  sed -n 's/.*last_url=//p' "$output_file" | tail -n1
}

check_opensearch_health() {
  ssh "$SERVER" bash -s -- "$PROJECT_NAME" <<'REMOTE' | jq -e '.status == "green" or .status == "yellow"' >/dev/null
set -euo pipefail
project_name="$1"
container_id="$(docker ps -q \
  --filter "label=com.docker.compose.project=${project_name}" \
  --filter "label=com.docker.compose.service=opensearch" | head -n1)"
if [ -z "$container_id" ]; then
  echo "Missing running opensearch container for project ${project_name}" >&2
  exit 1
fi
docker exec "$container_id" curl -sS "http://localhost:9200/_cluster/health"
REMOTE
}

check_public_search() {
  local url="${FRONTEND_URL%/}/search-results?q=python&limit=1"
  curl -sS "$url" | jq -e '.total >= 0 and (.degraded != true) and (.error_type == null)' >/dev/null
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
shift

case "$ENVIRONMENT" in
  prd)
    require_value WEB_SEARCH_PRD_SERVER "$DEFAULT_PRD_SERVER"
    SERVER="$DEFAULT_PRD_SERVER"
    PROJECT_NAME="$DEFAULT_PRD_PROJECT"
    FRONTEND_URL="$DEFAULT_PRD_FRONTEND_URL"
    STATE_FILE="$DEFAULT_PRD_STATE_FILE"
    ;;
  *)
    echo "Unsupported environment: $ENVIRONMENT" >&2
    usage
    exit 1
    ;;
esac

BATCH_SIZE="$DEFAULT_BATCH_SIZE"
SEGMENT_SIZE="$DEFAULT_SEGMENT_SIZE"
MAX_SEGMENTS=""
START_AFTER_URL=""
OPENSEARCH_URL="$DEFAULT_OPENSEARCH_URL"
INDEX_NAME=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --batch-size)
      BATCH_SIZE="${2:-}"
      shift 2
      ;;
    --segment-size)
      SEGMENT_SIZE="${2:-}"
      shift 2
      ;;
    --max-segments)
      MAX_SEGMENTS="${2:-}"
      shift 2
      ;;
    --start-after-url)
      START_AFTER_URL="${2:-}"
      shift 2
      ;;
    --state-file)
      STATE_FILE="${2:-}"
      shift 2
      ;;
    --opensearch-url)
      OPENSEARCH_URL="${2:-}"
      shift 2
      ;;
    --index-name)
      INDEX_NAME="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

require_cmd base64
require_cmd curl
require_cmd jq
require_cmd ssh
require_cmd tee

if ! [[ "$BATCH_SIZE" =~ ^[0-9]+$ ]] || [ "$BATCH_SIZE" -lt 1 ]; then
  echo "--batch-size must be a positive integer" >&2
  exit 1
fi
if ! [[ "$SEGMENT_SIZE" =~ ^[0-9]+$ ]] || [ "$SEGMENT_SIZE" -lt 1 ]; then
  echo "--segment-size must be a positive integer" >&2
  exit 1
fi
if [ -n "$MAX_SEGMENTS" ] && { ! [[ "$MAX_SEGMENTS" =~ ^[0-9]+$ ]] || [ "$MAX_SEGMENTS" -lt 1 ]; }; then
  echo "--max-segments must be a positive integer" >&2
  exit 1
fi

if [ -z "$START_AFTER_URL" ]; then
  START_AFTER_URL="$(read_state_value LAST_URL)"
fi
SEGMENTS_COMPLETED="$(read_state_value SEGMENTS_COMPLETED)"
if [ -z "$SEGMENTS_COMPLETED" ]; then
  SEGMENTS_COMPLETED=0
fi

echo "Target environment : ${ENVIRONMENT}"
echo "Server             : ${SERVER}"
echo "Compose project    : ${PROJECT_NAME}"
echo "State file         : ${STATE_FILE}"
echo "Batch size         : ${BATCH_SIZE}"
echo "Segment size       : ${SEGMENT_SIZE}"
echo "Max segments       : ${MAX_SEGMENTS:-unbounded}"
echo "Start after URL    : ${START_AFTER_URL:-<beginning>}"
echo "OpenSearch index   : ${INDEX_NAME:-documents}"

segments_run=0
current_start="$START_AFTER_URL"
while true; do
  if [ -n "$MAX_SEGMENTS" ] && [ "$segments_run" -ge "$MAX_SEGMENTS" ]; then
    echo "Reached max segments: ${MAX_SEGMENTS}"
    break
  fi

  output_file="$(mktemp)"
  echo "Starting segment $((segments_run + 1)) after: ${current_start:-<beginning>}"
  if ! run_segment "$current_start" "$output_file"; then
    last_url="$(extract_last_url "$output_file")"
    rm -f "$output_file"
    if [ -n "$last_url" ]; then
      write_state "$last_url" "$SEGMENTS_COMPLETED" "failed"
      echo "Segment failed; saved last_url=${last_url}" >&2
    fi
    exit 1
  fi

  last_url="$(extract_last_url "$output_file")"
  rm -f "$output_file"
  if [ -z "$last_url" ] || [ "$last_url" = "$current_start" ]; then
    echo "No new last_url emitted; rebuild appears complete."
    write_state "$current_start" "$SEGMENTS_COMPLETED" "complete"
    break
  fi

  SEGMENTS_COMPLETED=$((SEGMENTS_COMPLETED + 1))
  segments_run=$((segments_run + 1))
  write_state "$last_url" "$SEGMENTS_COMPLETED" "ok"

  echo "Checking OpenSearch health"
  check_opensearch_health
  echo "Checking public search"
  check_public_search
  echo "Segment complete; saved last_url=${last_url}"

  current_start="$last_url"
done
