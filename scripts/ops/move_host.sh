#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PRD_PROJECT="web-search-prd"
PRD_ENV_FILE="/etc/web-search/prd.env"
PRD_DATA_DIR="/srv/web-search/data"

# service|path inside the container|directory under PRD_DATA_DIR
DATA_MOUNTS=(
  "postgres|/var/lib/postgresql/data|postgres"
  "opensearch|/usr/share/opensearch/data|opensearch"
  "prometheus|/prometheus|prometheus"
  "grafana|/var/lib/grafana|grafana"
  "caddy|/data|caddy/data"
  "caddy|/config|caddy/config"
)

usage() {
  cat <<'USAGE'
Usage:
  move_host.sh copy <from> <to>
  move_host.sh switch <from> <to> <commit-ish>

Examples:
  ./scripts/ops/move_host.sh copy dev@old-host dev@new-host
  ./scripts/ops/move_host.sh switch dev@old-host dev@new-host main

Notes:
  - copy: copies the env file and the data of the stack on <from> while it keeps
    serving. Run it again to shorten the final copy.
  - switch: stops the stack on <from>, copies what changed, and deploys
    <commit-ish> on <to>. DNS still points at <from>; verify <to>, then switch DNS.
    To roll back, start the stopped containers on <from> again.
  - <to> must be prepared with setup_host.sh. <from> connects to <to> over SSH
    with the forwarded agent. Set WEB_SEARCH_MOVE_TO_ADDRESS when <from> must use
    a different address for <to>.
USAGE
}

refuse_running_stack() {
  if [ -n "$(ssh "$TO" "sudo docker ps -q --filter label=com.docker.compose.project=${PRD_PROJECT}")" ]; then
    echo "The stack is already running on ${TO}; refusing to overwrite its data." >&2
    exit 1
  fi
}

check_prepared() {
  if ! ssh "$TO" "command -v docker >/dev/null && test -d '${PRD_DATA_DIR}' && sudo test -d /etc/web-search"; then
    echo "${TO} is not prepared; run setup_host.sh first." >&2
    exit 1
  fi
}

copy_env() {
  ssh "$FROM" "sudo cat '${PRD_ENV_FILE}'" \
    | ssh "$TO" "sudo sh -c 'umask 077; cat > \"${PRD_ENV_FILE}\"'"
  echo "copied: ${PRD_ENV_FILE}"
}

copy_data() {
  local to_user
  local to_address
  to_user="$(ssh "$TO" id -un)"
  to_address="${WEB_SEARCH_MOVE_TO_ADDRESS:-${TO#*@}}"

  ssh -A "$FROM" bash -s -- "${to_user}@${to_address}" "$PRD_PROJECT" "$PRD_DATA_DIR" "${DATA_MOUNTS[@]}" <<'REMOTE'
set -euo pipefail

target="$1"
project="$2"
data_dir="$3"
shift 3

for entry in "$@"; do
  IFS='|' read -r service path subdir <<<"$entry"
  container="$(sudo docker ps -aq \
    --filter "label=com.docker.compose.project=${project}" \
    --filter "label=com.docker.compose.service=${service}" | head -n1)"
  source=""
  if [ -n "$container" ]; then
    source="$(sudo docker inspect --format "{{range .Mounts}}{{if eq .Destination \"${path}\"}}{{.Source}}{{end}}{{end}}" "$container")"
  fi
  if [ -z "$source" ]; then
    echo "skipped: ${service} ${path} (no data on this host)"
    continue
  fi
  source="$(sudo readlink -f "$source")"
  status=0
  output="$(sudo --preserve-env=SSH_AUTH_SOCK rsync -aH --numeric-ids --delete --stats \
    -e "ssh -o StrictHostKeyChecking=accept-new" --rsync-path="sudo rsync" \
    "${source}/" "${target}:${data_dir}/${subdir}/" 2>&1)" || status=$?
  # 24: files vanished during the copy, which is expected while the stack runs.
  if [ "$status" -ne 0 ] && [ "$status" -ne 24 ]; then
    printf '%s\n' "$output" >&2
    exit "$status"
  fi
  echo "copied: ${service} ${path} ($(printf '%s\n' "$output" | sed -n 's/^Total transferred file size: //p') transferred)"
done
REMOTE
}

stop_from() {
  ssh "$FROM" "sudo docker ps -q --filter label=com.docker.compose.project=${PRD_PROJECT} | xargs -r sudo docker stop" >/dev/null
  echo "stopped: the stack on ${FROM}"
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

COMMAND="${1:-}"
FROM="${2:-}"
TO="${3:-}"
REF="${4:-}"

case "$COMMAND" in
  copy)
    [ -n "$FROM" ] && [ -n "$TO" ] || { usage; exit 1; }
    check_prepared
    refuse_running_stack
    copy_env
    copy_data
    ;;
  switch)
    [ -n "$FROM" ] && [ -n "$TO" ] && [ -n "$REF" ] || { usage; exit 1; }
    check_prepared
    refuse_running_stack
    stop_from
    copy_env
    copy_data
    WEB_SEARCH_PRD_SERVER="$TO" "${SCRIPT_DIR}/deploy_compose.sh" prd "$REF"
    echo "Deployed on ${TO}. Verify it, then point DNS at it. ${FROM} keeps its stopped stack for rollback."
    ;;
  *)
    usage
    exit 1
    ;;
esac
