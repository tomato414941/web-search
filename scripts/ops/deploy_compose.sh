#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PRD_ROOT="/srv/web-search"
PRD_ENV_FILE="/etc/web-search/prd.env"

usage() {
  cat <<'USAGE'
Usage:
  deploy_compose.sh prd <commit-ish> [service ...]

Examples:
  ./scripts/ops/deploy_compose.sh prd main
  ./scripts/ops/deploy_compose.sh prd 0123abcd
  ./scripts/ops/deploy_compose.sh prd main caddy grafana

Notes:
  - Deploys deploy/prd from the resolved commit; each service runs the image pinned there.
  - Selected services are deployed without starting dependencies or removing other services.
  - WEB_SEARCH_PRD_SERVER is the SSH destination of the production host.
  - The host must be prepared with scripts/ops/setup_host.sh and have /etc/web-search/prd.env.
USAGE
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

ENVIRONMENT="${1:-}"
TARGET_REF="${2:-}"
if [ "$ENVIRONMENT" != "prd" ] || [ -z "$TARGET_REF" ]; then
  usage
  exit 1
fi
shift 2
SERVICES=("$@")
for service in "${SERVICES[@]}"; do
  if [[ ! "$service" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]]; then
    echo "Invalid service name: $service" >&2
    exit 1
  fi
done

SERVER="${WEB_SEARCH_PRD_SERVER:-}"
if [ -z "$SERVER" ]; then
  echo "Missing required environment variable: WEB_SEARCH_PRD_SERVER" >&2
  exit 1
fi

require_cmd git
require_cmd ssh

COMMIT="$(git -C "$REPO_ROOT" rev-parse "${TARGET_REF}^{commit}")"
RELEASE_DIR="${PRD_ROOT}/releases/${COMMIT}"

echo "Target environment : ${ENVIRONMENT}"
echo "Commit             : ${COMMIT}"
if [ "${#SERVICES[@]}" -gt 0 ]; then
  printf 'Selected services  : %s\n' "${SERVICES[*]}"
fi

git -C "$REPO_ROOT" archive --format=tar "$COMMIT" deploy/prd \
  | ssh "$SERVER" "sudo mkdir -p '$RELEASE_DIR' && sudo tar -xf - -C '$RELEASE_DIR' --strip-components=2"

ssh "$SERVER" bash -s -- "$PRD_ROOT" "$RELEASE_DIR" "$PRD_ENV_FILE" "$COMMIT" "${SERVICES[@]}" <<'REMOTE'
set -euo pipefail

prd_root="$1"
release_dir="$2"
env_file="$3"
commit="$4"
shift 4
services=("$@")

if ! sudo test -f "$env_file"; then
  echo "Missing env file on remote host: $env_file" >&2
  exit 1
fi

compose=(sudo docker compose --project-directory "$release_dir" -f "$release_dir/compose.yml" --env-file "$env_file")
if [ "${#services[@]}" -gt 0 ]; then
  available_services="$("${compose[@]}" config --services)"
  for service in "${services[@]}"; do
    if ! grep -Fxq -- "$service" <<<"$available_services"; then
      echo "Unknown service: $service" >&2
      exit 1
    fi
  done
  "${compose[@]}" pull --quiet "${services[@]}"
  "${compose[@]}" up -d --no-deps --wait --wait-timeout 180 "${services[@]}"
  "${compose[@]}" ps --services --status running "${services[@]}"
else
  "${compose[@]}" pull --quiet
  "${compose[@]}" up -d --remove-orphans
  "${compose[@]}" ps
fi

sudo ln -sfn "$release_dir" "$prd_root/current"
printf 'DEPLOY_COMMIT=%s\nDEPLOY_RELEASE_DIR=%s\n' "$commit" "$release_dir" \
  | sudo tee "$prd_root/deployed.env" >/dev/null
REMOTE
