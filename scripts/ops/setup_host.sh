#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  setup_host.sh <ssh-destination>

Example:
  ./scripts/ops/setup_host.sh dev@web-search-ovh-sg

Notes:
  - Prepares an Ubuntu host to run deploy/prd: Docker, firewall rules for
    HTTP/HTTPS, the OpenSearch memory map limit, and /srv/web-search.
  - The SSH user must have passwordless sudo. It is added to the docker group.
  - Safe to run again on a prepared host.
USAGE
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi
if [ -z "${1:-}" ]; then
  usage
  exit 1
fi

SERVER="$1"

ssh "$SERVER" 'sudo bash -s -- "$(id -un)"' <<'REMOTE'
set -euo pipefail

operator="$1"
export DEBIAN_FRONTEND=noninteractive

if ! command -v docker >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl >/dev/null
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
fi

daemon_config='{
  "live-restore": true,
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}'
if [ "$(cat /etc/docker/daemon.json 2>/dev/null)" != "$daemon_config" ]; then
  printf '%s\n' "$daemon_config" > /etc/docker/daemon.json
  systemctl restart docker
fi
usermod -aG docker "$operator"

# OpenSearch refuses to start below this memory map limit.
if [ "$(sysctl -n vm.max_map_count)" -lt 262144 ]; then
  echo "vm.max_map_count = 262144" > /etc/sysctl.d/90-opensearch.conf
  sysctl -q --system
fi

if ufw status | grep -q "^Status: active"; then
  ufw allow 80/tcp comment "web-search HTTP" >/dev/null
  ufw allow 443/tcp comment "web-search HTTPS" >/dev/null
  ufw allow 443/udp comment "web-search HTTP/3" >/dev/null
fi

install -d -m 0755 /srv/web-search /srv/web-search/releases /srv/web-search/data
install -d -m 0700 /etc/web-search
make_data_dir() {
  [ -d "/srv/web-search/data/$1" ] || install -d -m "$2" -o "$3" -g "$4" "/srv/web-search/data/$1"
}
make_data_dir postgres 0700 999 999
make_data_dir opensearch 0750 1000 1000
make_data_dir prometheus 0755 65534 65534
make_data_dir grafana 0755 472 0
make_data_dir caddy 0755 0 0
make_data_dir caddy/data 0700 0 0
make_data_dir caddy/config 0700 0 0

echo "0 4 * * * root docker image prune -a --filter until=48h -f >/dev/null 2>&1" > /etc/cron.d/web-search-docker-prune

echo "docker: $(docker --version)"
echo "compose: $(docker compose version --short)"
echo "vm.max_map_count: $(sysctl -n vm.max_map_count)"
echo "env file: $([ -f /etc/web-search/prd.env ] && echo present || echo missing)"
REMOTE
