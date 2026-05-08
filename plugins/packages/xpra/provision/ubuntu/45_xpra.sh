#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg xpra

log "### 45_xpra: installing Xpra server from upstream repo"

if command -v xpra >/dev/null 2>&1; then
  log "xpra already installed — skipping"
  exit 0
fi

apt_update_once
apt_install xauth x11-apps

REPO_KEY=/etc/apt/trusted.gpg.d/xpra.asc
REPO_LIST=/etc/apt/sources.list.d/xpra.list

if [ ! -f "$REPO_KEY" ]; then
  log "### 45_xpra: adding xpra.org GPG key"
  curl -fsSL https://xpra.org/xpra.asc | sudo tee "$REPO_KEY" >/dev/null
fi

if [ ! -f "$REPO_LIST" ]; then
  log "### 45_xpra: adding xpra.org apt repo"
  # shellcheck disable=SC1091
  DIST=$(. /etc/os-release && echo "$VERSION_CODENAME")
  case "$DIST" in
    resolute) DIST=noble ;;
  esac
  ARCH=$(dpkg --print-architecture)
  echo "deb [arch=$ARCH] https://xpra.org/ $DIST main" | sudo tee "$REPO_LIST" >/dev/null
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -y
fi

if sudo DEBIAN_FRONTEND=noninteractive apt-get install -y xpra xpra-x11 2>&1; then
log "### 45_xpra: done"
else
  log "### 45_xpra: WARNING — xpra packages incompatible with this OS, skipping"
  log "### 45_xpra: (xpra requires python3 < 3.13; this system has python3 $(python3 -c 'import sys; print(sys.version)'))"
  sudo rm -f /etc/apt/sources.list.d/xpra.list
  exit 0
fi
