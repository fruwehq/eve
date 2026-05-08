#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg discord

if [ "$(dpkg --print-architecture)" != "amd64" ]; then
  log "Discord desktop client is only available on amd64 — skipping"
  exit 0
fi

log "### discord: installing Discord"

if command -v discord >/dev/null 2>&1 || dpkg -s discord >/dev/null 2>&1; then
  log "discord already installed — skipping"
  exit 0
fi

apt_install wget

deb="$DOWNLOADS_DIR/discord.deb"
wget -qO "$deb" 'https://discord.com/api/download?platform=linux&format=deb'
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$deb"

log "### discord: done"
