#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg vnc

if ! is_desktop; then
  log "### 46_vnc: headless OS — skipping"
  exit 0
fi

log "### 46_vnc: installing TigerVNC server"

if command -v vncserver >/dev/null 2>&1; then
  log "vncserver already installed — skipping"
  exit 0
fi

apt_install tigervnc-standalone-server tigervnc-common

log "### 46_vnc: done"
