#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg steam

if ! is_desktop; then
  log "### 70_steam: headless OS — skipping"
  exit 0
fi

if [ "$(dpkg --print-architecture)" != "amd64" ]; then
  log "Steam only available on amd64 — skipping"
  exit 0
fi

log "### 70_steam: installing Steam"

if command -v steam >/dev/null 2>&1 || dpkg -l steam-launcher >/dev/null 2>&1; then
  log "steam already installed — skipping"
  exit 0
fi

sudo dpkg --add-architecture i386
apt_update_once

sudo add-apt-repository -y multiverse || true
sudo DEBIAN_FRONTEND=noninteractive apt-get update -y

echo "steam steam/question select I AGREE" | sudo debconf-set-selections
echo "steam steam/license note" | sudo debconf-set-selections
apt_install steam-installer

log "### 70_steam: done"
