#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg waypipe

log "### 47_waypipe: installing experimental Wayland remote-app tooling"

if command -v waypipe >/dev/null 2>&1; then
  log "waypipe already installed — skipping"
  exit 0
fi

apt_update_once
apt_install waypipe weston xwayland foot x11-apps zenity

log "### 47_waypipe: done"
