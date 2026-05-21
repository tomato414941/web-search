#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DEFAULT_PRD_SERVER="${WEB_SEARCH_PRD_SERVER:-}"
DEFAULT_PRD_ENV_FILE="${WEB_SEARCH_PRD_ENV_FILE:-}"
DEFAULT_PRD_REPO_PATH="${WEB_SEARCH_PRD_REPO_PATH:-}"
DEFAULT_PRD_PROJECT="${WEB_SEARCH_PRD_PROJECT:-web-search-prd}"
DEFAULT_PRD_OPENSEARCH_DATA_DIR="${WEB_SEARCH_PRD_OPENSEARCH_DATA_DIR:-/var/lib/web-search/opensearch-data}"

usage() {
  cat <<'USAGE'
Usage:
  deploy_compose.sh prd <commit-ish>

Examples:
  ./scripts/ops/deploy_compose.sh prd main
  ./scripts/ops/deploy_compose.sh prd 0123abcd

Notes:
  - Deploys the resolved source tree with docker compose --build on the target host.
  - The remote host must have docker, docker compose, and tar available.
  - The env file must already exist on the remote host.
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

resolve_commit() {
  local ref="$1"
  git -C "$REPO_ROOT" rev-parse "${ref}^{commit}"
}

upload_remote_bundle() {
  local bundle_dir="$1"

  ssh "$SERVER" "rm -rf '$bundle_dir' && mkdir -p '$bundle_dir'"
  git -C "$REPO_ROOT" archive --format=tar "$EXPECTED_COMMIT" \
    | ssh "$SERVER" "tar -xf - -C '$bundle_dir'"
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
      STATE_FILE="${REPO_PATH}/.deploy-state/prd.env"
      BUNDLE_ROOT="${REPO_PATH}/.compose-bundles/${PROJECT_NAME}"
      OPENSEARCH_DATA_DIR="$DEFAULT_PRD_OPENSEARCH_DATA_DIR"
      ;;
    *)
      echo "Unsupported environment: $ENVIRONMENT" >&2
      usage
      exit 1
      ;;
  esac

  if is_local_server; then
    REPO_PATH="$REPO_ROOT"
  fi
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

ENVIRONMENT="${1:-}"
TARGET_REF="${2:-}"
if [ -z "$ENVIRONMENT" ] || [ -z "$TARGET_REF" ]; then
  usage
  exit 1
fi

require_cmd git

set_environment_config
EXPECTED_COMMIT="$(resolve_commit "$TARGET_REF")"

if ! is_local_server; then
  require_cmd ssh
  require_cmd tar
fi

echo "Target environment : ${ENVIRONMENT}"
echo "Expected commit    : ${EXPECTED_COMMIT}"
echo "Server             : ${SERVER}"
echo "Repo path          : ${REPO_PATH}"
echo "State file         : ${STATE_FILE}"
echo "Compose project    : ${PROJECT_NAME}"
echo "Env file           : ${ENV_FILE}"
echo "Deploy mode        : source build"
if [ -n "${OPENSEARCH_DATA_DIR:-}" ]; then
  echo "OpenSearch data dir: ${OPENSEARCH_DATA_DIR}"
fi

REMOTE_EXTRA_COMPOSE_FILE="${EXTRA_COMPOSE_FILE:-__NONE__}"
REMOTE_OPENSEARCH_DATA_DIR="${OPENSEARCH_DATA_DIR:-}"
if is_local_server; then
  bash -s -- \
    "$REPO_PATH" \
    "$STATE_FILE" \
    "$EXPECTED_COMMIT" \
    "$PROJECT_NAME" \
    "$ENV_FILE" \
    "$REMOTE_EXTRA_COMPOSE_FILE" \
    "$REMOTE_OPENSEARCH_DATA_DIR" <<'REMOTE'
set -euo pipefail

repo_path="$1"
state_file="$2"
commit="$3"
project_name="$4"
env_file="$5"
extra_compose_file="${6:-}"
opensearch_data_dir="${7:-}"

if [ "$extra_compose_file" = "__NONE__" ]; then
  extra_compose_file=""
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Missing required command on remote host: docker" >&2
  exit 1
fi

if [ ! -f "$env_file" ]; then
  echo "Missing env file on remote host: $env_file" >&2
  exit 1
fi

if [ ! -d "$repo_path/.git" ]; then
  echo "Missing git checkout on local host: $repo_path" >&2
  exit 1
fi

git config --global --add safe.directory "$repo_path"

cd "$repo_path"
current_commit="$(git rev-parse HEAD)"
if [ "$current_commit" != "$commit" ]; then
  echo "Local checkout is at ${current_commit}, expected ${commit}" >&2
  exit 1
fi

compose_args=(
  -p "$project_name"
  -f docker-compose.yml
  -f deploy/compose.host.yml
)
if [ -n "$extra_compose_file" ] && [ -f "$extra_compose_file" ]; then
  compose_args+=(-f "$extra_compose_file")
fi

if [ -n "$opensearch_data_dir" ]; then
  export WEB_SEARCH_PRD_OPENSEARCH_DATA_DIR="$opensearch_data_dir"
fi

if [ -n "$opensearch_data_dir" ]; then
  if [ -d "$opensearch_data_dir" ] && [ "$(stat -c '%u:%g' "$opensearch_data_dir")" = "1000:1000" ]; then
    :
  elif [ "$(id -u)" -eq 0 ]; then
    install -d -o 1000 -g 1000 -m 0750 "$opensearch_data_dir"
  elif command -v sudo >/dev/null 2>&1; then
    sudo install -d -o 1000 -g 1000 -m 0750 "$opensearch_data_dir"
  else
    echo "OpenSearch data dir must exist and be owned by 1000:1000: $opensearch_data_dir" >&2
    exit 1
  fi
fi

docker compose \
  "${compose_args[@]}" \
  --env-file "$env_file" \
  up -d --build --remove-orphans

docker compose \
  "${compose_args[@]}" \
  --env-file "$env_file" \
  ps

mkdir -p "$(dirname "$state_file")"
cat > "$state_file" <<STATE
DEPLOY_COMMIT=${commit}
DEPLOY_MODE=source-build
DEPLOY_PROJECT_NAME=${project_name}
DEPLOY_BUNDLE_DIR=${repo_path}
STATE
REMOTE
else
  REMOTE_BUNDLE_DIR="${BUNDLE_ROOT}/${EXPECTED_COMMIT}"
  upload_remote_bundle "$REMOTE_BUNDLE_DIR"
  ssh -A "$SERVER" bash -s -- \
    "$REMOTE_BUNDLE_DIR" \
    "$STATE_FILE" \
    "$EXPECTED_COMMIT" \
    "$PROJECT_NAME" \
    "$ENV_FILE" \
    "$REMOTE_EXTRA_COMPOSE_FILE" \
    "$REMOTE_OPENSEARCH_DATA_DIR" <<'REMOTE'
set -euo pipefail

bundle_dir="$1"
state_file="$2"
commit="$3"
project_name="$4"
env_file="$5"
extra_compose_file="${6:-}"
opensearch_data_dir="${7:-}"

if [ "$extra_compose_file" = "__NONE__" ]; then
  extra_compose_file=""
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Missing required command on remote host: docker" >&2
  exit 1
fi

if ! command -v tar >/dev/null 2>&1; then
  echo "Missing required command on remote host: tar" >&2
  exit 1
fi

if [ ! -f "$env_file" ]; then
  echo "Missing env file on remote host: $env_file" >&2
  exit 1
fi

if [ ! -d "$bundle_dir" ]; then
  echo "Missing compose bundle on remote host: $bundle_dir" >&2
  exit 1
fi

cd "$bundle_dir"

compose_args=(
  -p "$project_name"
  -f docker-compose.yml
  -f deploy/compose.host.yml
)
if [ -n "$extra_compose_file" ] && [ -f "$extra_compose_file" ]; then
  compose_args+=(-f "$extra_compose_file")
fi

if [ -n "$opensearch_data_dir" ]; then
  export WEB_SEARCH_PRD_OPENSEARCH_DATA_DIR="$opensearch_data_dir"
fi

if [ -n "$opensearch_data_dir" ]; then
  if [ -d "$opensearch_data_dir" ] && [ "$(stat -c '%u:%g' "$opensearch_data_dir")" = "1000:1000" ]; then
    :
  elif [ "$(id -u)" -eq 0 ]; then
    install -d -o 1000 -g 1000 -m 0750 "$opensearch_data_dir"
  elif command -v sudo >/dev/null 2>&1; then
    sudo install -d -o 1000 -g 1000 -m 0750 "$opensearch_data_dir"
  else
    echo "OpenSearch data dir must exist and be owned by 1000:1000: $opensearch_data_dir" >&2
    exit 1
  fi
fi

docker compose \
  "${compose_args[@]}" \
  --env-file "$env_file" \
  up -d --build --remove-orphans

docker compose \
  "${compose_args[@]}" \
  --env-file "$env_file" \
  ps

mkdir -p "$(dirname "$state_file")"
cat > "$state_file" <<STATE
DEPLOY_COMMIT=${commit}
DEPLOY_MODE=source-build
DEPLOY_PROJECT_NAME=${project_name}
DEPLOY_BUNDLE_DIR=${bundle_dir}
STATE
REMOTE
fi
