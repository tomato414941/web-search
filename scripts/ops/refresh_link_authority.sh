#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  refresh_link_authority.sh [--batch-size 500] [--opensearch-url URL]

Runs the link authority refresh operation:
  1. calculate page-level and domain-level link authority
  2. rebuild the OpenSearch search projection from current source data

Requires:
  DATABASE_URL
  OPENSEARCH_URL, unless --opensearch-url is supplied
USAGE
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

for arg in "$@"; do
  if [ "$arg" = "--dry-run" ]; then
    echo "refresh_link_authority.sh does not support --dry-run because authority calculation mutates rank tables." >&2
    echo "Use web-search-rebuild-search-projection --dry-run to inspect projection rebuild only." >&2
    exit 1
  fi
done

uv run --package web-search-web-model web-search-calc-pagerank
uv run --package web-search-indexer web-search-rebuild-search-projection "$@"
