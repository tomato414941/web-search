#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PRD_ROOT="/srv/web-search"
PRD_ENV_FILE="/etc/web-search/prd.env"

usage() {
  cat <<'USAGE'
Usage:
  deploy_compose.sh prd <commit-ish>

Examples:
  ./scripts/ops/deploy_compose.sh prd main
  ./scripts/ops/deploy_compose.sh prd 0123abcd

Notes:
  - Deploys deploy/prd from the resolved commit; each service runs the image pinned there.
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
echo "Server             : ${SERVER}"
echo "Release directory  : ${RELEASE_DIR}"

git -C "$REPO_ROOT" archive --format=tar "$COMMIT" deploy/prd \
  | ssh "$SERVER" "sudo rm -rf '$RELEASE_DIR' && sudo mkdir -p '$RELEASE_DIR' && sudo tar -xf - -C '$RELEASE_DIR' --strip-components=2"

ssh "$SERVER" bash -s -- "$PRD_ROOT" "$RELEASE_DIR" "$PRD_ENV_FILE" "$COMMIT" <<'REMOTE'
set -euo pipefail

prd_root="$1"
release_dir="$2"
env_file="$3"
commit="$4"

if ! sudo test -f "$env_file"; then
  echo "Missing env file on remote host: $env_file" >&2
  exit 1
fi

compose=(sudo docker compose --project-directory "$release_dir" -f "$release_dir/compose.yml" --env-file "$env_file")
"${compose[@]}" pull --quiet
"${compose[@]}" up -d --remove-orphans
"${compose[@]}" ps

sudo ln -sfn "$release_dir" "$prd_root/current"
printf 'DEPLOY_COMMIT=%s\nDEPLOY_RELEASE_DIR=%s\n' "$commit" "$release_dir" \
  | sudo tee "$prd_root/deployed.env" >/dev/null
REMOTE
