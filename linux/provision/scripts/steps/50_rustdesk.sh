#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg rustdesk

if ! is_desktop; then
  log "### 50_rustdesk: headless OS — skipping"
  exit 0
fi

log "### 50_rustdesk: installing RustDesk"

if command -v rustdesk >/dev/null 2>&1; then
  log "rustdesk already installed — skipping"
  exit 0
fi

arch=$(dpkg --print-architecture)
case "$arch" in
  amd64) asset="rustdesk-1.3.9-x86_64.deb" ;;
  arm64) asset="rustdesk-1.3.9-aarch64.deb" ;;
  *) log "unsupported arch for RustDesk: $arch"; exit 1 ;;
esac

deb="$DOWNLOADS_DIR/$asset"
download "https://github.com/rustdesk/rustdesk/releases/download/1.3.9/$asset" "$deb"
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$deb"

log "### 50_rustdesk: done"
