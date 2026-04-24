#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg xpra

log "### 45_xpra: installing Xpra server"

if command -v xpra >/dev/null 2>&1; then
  log "xpra already installed — skipping"
  exit 0
fi

apt_update_once
apt_install xpra xpra-html5 xauth x11-apps

log "### 45_xpra: done"
