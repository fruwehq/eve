#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg docker

log "### 10_docker: installing Docker CE"

if command -v docker >/dev/null 2>&1; then
  log "docker already installed — skipping"
  exit 0
fi

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --batch --yes --dearmor -o /etc/apt/keyrings/docker.gpg

# shellcheck disable=SC1091
codename=$(. /etc/os-release && echo "$VERSION_CODENAME")
arch=$(dpkg --print-architecture)
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu %s stable\n' \
  "$arch" "$codename" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo DEBIAN_FRONTEND=noninteractive apt-get update -y
apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker "$USER" || true

log "### 10_docker: done"
