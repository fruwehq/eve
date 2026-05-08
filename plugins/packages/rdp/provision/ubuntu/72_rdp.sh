#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg rdp

log "### 72_rdp: installing xrdp"

if command -v xrdp >/dev/null 2>&1 || dpkg -s xrdp >/dev/null 2>&1; then
  log "xrdp already installed — skipping"
  exit 0
fi

apt_install xrdp
sudo systemctl enable --now xrdp

log "### 72_rdp: done"
