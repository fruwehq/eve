#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg sunshine

if ! is_desktop; then
  log "### 60_sunshine: headless OS — skipping"
  exit 0
fi

log "### 60_sunshine: installing LizardByte Sunshine"

if command -v sunshine >/dev/null 2>&1; then
  log "sunshine already installed — skipping"
  exit 0
fi

arch=$(dpkg --print-architecture)
# shellcheck disable=SC1091
codename=$(. /etc/os-release && echo "$VERSION_CODENAME")
case "$arch-$codename" in
  amd64-noble)  asset="sunshine-ubuntu-24.04-amd64.deb" ;;
  arm64-noble)  asset="sunshine-ubuntu-24.04-arm64.deb" ;;
  amd64-jammy)  asset="sunshine-ubuntu-22.04-amd64.deb" ;;
  arm64-jammy)  asset="sunshine-ubuntu-22.04-arm64.deb" ;;
  *) log "no known Sunshine package for $arch/$codename"; exit 1 ;;
esac

api="https://api.github.com/repos/LizardByte/Sunshine/releases/latest"
url=$(curl -fsSL "$api" \
  | jq -r --arg name "$asset" '.assets[] | select(.name == $name) | .browser_download_url' \
  | head -n1)

if [ -z "$url" ]; then
  log "could not resolve Sunshine asset $asset from latest release"
  exit 1
fi

deb="$DOWNLOADS_DIR/$asset"
download "$url" "$deb"
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$deb"

log "### 60_sunshine: done (configure credentials via Sunshine web UI)"
