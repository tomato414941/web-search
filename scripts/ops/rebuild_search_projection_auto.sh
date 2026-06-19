#!/usr/bin/env bash
set -euo pipefail

DEFAULT_SEGMENT_SIZE=10000
DEFAULT_BATCH_SIZE=100
DEFAULT_PAUSE_SECONDS=30
DEFAULT_MAX_WAIT_SECONDS=900
DEFAULT_OPENSEARCH_MEM_LIMIT_PCT=85
DEFAULT_POSTGRES_MEM_LIMIT_PCT=95
DEFAULT_INDEXER_MEM_LIMIT_PCT=80
DEFAULT_PRD_PROJECT="${WEB_SEARCH_PRD_PROJECT:-web-search-prd}"

usage() {
  cat <<'USAGE'
Usage:
  rebuild_search_projection_auto.sh prd [options]

Options:
  --batch-size N                  Rebuild CLI batch size. Default: 100.
  --segment-size N                Documents per segment. Default: 10000.
  --max-segments N                Stop after N successful segments.
  --pause-seconds N               Sleep between segments. Default: 30.
  --max-wait-seconds N            Stop after waiting this long for memory. Default: 900.
  --opensearch-mem-limit-pct N    Wait while OpenSearch memory is >= N. Default: 85.
  --postgres-mem-limit-pct N      Wait while PostgreSQL memory is >= N. Default: 95.
  --indexer-mem-limit-pct N       Wait while indexer memory is >= N. Default: 80.
  --state-file PATH               Remote rebuild state file.
  --opensearch-url URL            OpenSearch URL inside the indexer container.
  --index-name NAME               OpenSearch index or alias name to rebuild.

Environment:
  WEB_SEARCH_PRD_SERVER           Required for prd.
  WEB_SEARCH_PRD_PROJECT          Compose project name. Default: web-search-prd.

Notes:
  - Calls rebuild_search_projection_segments.sh with --max-segments 1.
  - Continues until --max-segments is reached, the projection completes, or a
    guard condition fails.
  - Memory guards are checked before each segment.
USAGE
}

require_value() {
  local name="$1"
  local value="$2"
  if [ -z "$value" ]; then
    echo "Missing required environment variable: $name" >&2
    exit 1
  fi
}

require_cmd() {
  local command="$1"
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required command: $command" >&2
    exit 1
  fi
}

require_positive_integer() {
  local name="$1"
  local value="$2"
  if ! [[ "$value" =~ ^[0-9]+$ ]] || [ "$value" -lt 1 ]; then
    echo "${name} must be a positive integer" >&2
    exit 1
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

read_mem_percents() {
  ssh "$SERVER" bash -s -- "$PROJECT_NAME" <<'REMOTE'
set -euo pipefail
project_name="$1"
for service in indexer opensearch postgres; do
  container_id="$(docker ps -q \
    --filter "label=com.docker.compose.project=${project_name}" \
    --filter "label=com.docker.compose.service=${service}" | head -n1)"
  if [ -z "$container_id" ]; then
    echo "Missing running ${service} container for project ${project_name}" >&2
    exit 1
  fi
  mem_percent="$(docker stats --no-stream --format '{{.MemPerc}}' "$container_id" | tr -d '%')"
  printf '%s=%s\n' "$service" "$mem_percent"
done
REMOTE
}

mem_floor() {
  printf '%s\n' "$1" | awk '{ printf "%d\n", $1 }'
}

wait_for_memory() {
  local waited=0
  local mem_stats
  local indexer_pct
  local opensearch_pct
  local postgres_pct
  local indexer_floor
  local opensearch_floor
  local postgres_floor

  while true; do
    mem_stats="$(read_mem_percents)"
    indexer_pct="$(printf '%s\n' "$mem_stats" | sed -n 's/^indexer=//p')"
    opensearch_pct="$(printf '%s\n' "$mem_stats" | sed -n 's/^opensearch=//p')"
    postgres_pct="$(printf '%s\n' "$mem_stats" | sed -n 's/^postgres=//p')"
    indexer_floor="$(mem_floor "$indexer_pct")"
    opensearch_floor="$(mem_floor "$opensearch_pct")"
    postgres_floor="$(mem_floor "$postgres_pct")"

    echo "Memory: indexer=${indexer_pct}% opensearch=${opensearch_pct}% postgres=${postgres_pct}%"

    if [ "$indexer_floor" -lt "$INDEXER_MEM_LIMIT_PCT" ] \
      && [ "$opensearch_floor" -lt "$OPENSEARCH_MEM_LIMIT_PCT" ] \
      && [ "$postgres_floor" -lt "$POSTGRES_MEM_LIMIT_PCT" ]; then
      return 0
    fi

    if [ "$waited" -ge "$MAX_WAIT_SECONDS" ]; then
      echo "Memory guard did not clear within ${MAX_WAIT_SECONDS}s; stopping before next segment." >&2
      return 1
    fi

    echo "Memory guard active; sleeping ${PAUSE_SECONDS}s"
    sleep "$PAUSE_SECONDS"
    waited=$((waited + PAUSE_SECONDS))
  done
}

run_one_segment() {
  local args=(
    prd
    --batch-size "$BATCH_SIZE"
    --segment-size "$SEGMENT_SIZE"
    --max-segments 1
  )
  if [ -n "$STATE_FILE_ARG" ]; then
    args+=(--state-file "$STATE_FILE_ARG")
  fi
  if [ -n "$OPENSEARCH_URL" ]; then
    args+=(--opensearch-url "$OPENSEARCH_URL")
  fi
  if [ -n "$INDEX_NAME" ]; then
    args+=(--index-name "$INDEX_NAME")
  fi

  "$SCRIPT_DIR/rebuild_search_projection_segments.sh" "${args[@]}"
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
    require_value WEB_SEARCH_PRD_SERVER "${WEB_SEARCH_PRD_SERVER:-}"
    SERVER="$WEB_SEARCH_PRD_SERVER"
    PROJECT_NAME="$DEFAULT_PRD_PROJECT"
    STATE_FILE="${WEB_SEARCH_PRD_REBUILD_STATE_FILE:-/srv/web-search/.maintenance/search-projection-rebuild.env}"
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
PAUSE_SECONDS="$DEFAULT_PAUSE_SECONDS"
MAX_WAIT_SECONDS="$DEFAULT_MAX_WAIT_SECONDS"
OPENSEARCH_MEM_LIMIT_PCT="$DEFAULT_OPENSEARCH_MEM_LIMIT_PCT"
POSTGRES_MEM_LIMIT_PCT="$DEFAULT_POSTGRES_MEM_LIMIT_PCT"
INDEXER_MEM_LIMIT_PCT="$DEFAULT_INDEXER_MEM_LIMIT_PCT"
STATE_FILE_ARG=""
OPENSEARCH_URL=""
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
    --pause-seconds)
      PAUSE_SECONDS="${2:-}"
      shift 2
      ;;
    --max-wait-seconds)
      MAX_WAIT_SECONDS="${2:-}"
      shift 2
      ;;
    --opensearch-mem-limit-pct)
      OPENSEARCH_MEM_LIMIT_PCT="${2:-}"
      shift 2
      ;;
    --postgres-mem-limit-pct)
      POSTGRES_MEM_LIMIT_PCT="${2:-}"
      shift 2
      ;;
    --indexer-mem-limit-pct)
      INDEXER_MEM_LIMIT_PCT="${2:-}"
      shift 2
      ;;
    --state-file)
      STATE_FILE_ARG="${2:-}"
      STATE_FILE="$STATE_FILE_ARG"
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

require_cmd awk
require_cmd sed
require_cmd ssh

require_positive_integer "--batch-size" "$BATCH_SIZE"
require_positive_integer "--segment-size" "$SEGMENT_SIZE"
require_positive_integer "--pause-seconds" "$PAUSE_SECONDS"
require_positive_integer "--max-wait-seconds" "$MAX_WAIT_SECONDS"
require_positive_integer "--opensearch-mem-limit-pct" "$OPENSEARCH_MEM_LIMIT_PCT"
require_positive_integer "--postgres-mem-limit-pct" "$POSTGRES_MEM_LIMIT_PCT"
require_positive_integer "--indexer-mem-limit-pct" "$INDEXER_MEM_LIMIT_PCT"
if [ -n "$MAX_SEGMENTS" ]; then
  require_positive_integer "--max-segments" "$MAX_SEGMENTS"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Target environment       : ${ENVIRONMENT}"
echo "Server                   : ${SERVER}"
echo "Compose project          : ${PROJECT_NAME}"
echo "State file               : ${STATE_FILE}"
echo "Batch size               : ${BATCH_SIZE}"
echo "Segment size             : ${SEGMENT_SIZE}"
echo "Max segments             : ${MAX_SEGMENTS:-unbounded}"
echo "Pause seconds            : ${PAUSE_SECONDS}"
echo "Max wait seconds         : ${MAX_WAIT_SECONDS}"
echo "OpenSearch memory limit  : ${OPENSEARCH_MEM_LIMIT_PCT}%"
echo "PostgreSQL memory limit  : ${POSTGRES_MEM_LIMIT_PCT}%"
echo "Indexer memory limit     : ${INDEXER_MEM_LIMIT_PCT}%"
echo "OpenSearch index         : ${INDEX_NAME:-documents}"

segments_run=0
while true; do
  if [ -n "$MAX_SEGMENTS" ] && [ "$segments_run" -ge "$MAX_SEGMENTS" ]; then
    echo "Reached max segments: ${MAX_SEGMENTS}"
    break
  fi

  previous_status="$(read_state_value LAST_STATUS)"
  if [ "$previous_status" = "complete" ]; then
    echo "Projection rebuild is already marked complete."
    break
  fi

  wait_for_memory

  previous_url="$(read_state_value LAST_URL)"
  echo "Starting guarded segment $((segments_run + 1)) after: ${previous_url:-<beginning>}"
  run_one_segment

  segments_run=$((segments_run + 1))
  current_status="$(read_state_value LAST_STATUS)"
  current_url="$(read_state_value LAST_URL)"
  echo "Guarded segment complete: status=${current_status:-unknown} last_url=${current_url:-<empty>}"

  if [ "$current_status" = "complete" ]; then
    echo "Projection rebuild marked complete."
    break
  fi
  if [ "$current_status" != "ok" ]; then
    echo "Projection rebuild stopped with status=${current_status:-unknown}" >&2
    exit 1
  fi
  if [ "$current_url" = "$previous_url" ]; then
    echo "State did not advance; stopping to avoid a retry loop." >&2
    exit 1
  fi

  sleep "$PAUSE_SECONDS"
done
