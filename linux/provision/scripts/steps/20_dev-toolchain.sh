#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg dev-toolchain

log "### 20_dev-toolchain: build tools + language toolchains"

apt_update_once
apt_install build-essential pkg-config libssl-dev python3 python3-pip python3-venv

if ! command -v node >/dev/null 2>&1; then
  log "installing Node.js (NodeSource LTS)"
  download https://deb.nodesource.com/setup_lts.x "$DOWNLOADS_DIR/nodesource_setup_lts.sh"
  sudo -E bash "$DOWNLOADS_DIR/nodesource_setup_lts.sh"
  apt_install nodejs
fi

if ! command -v rustc >/dev/null 2>&1; then
  log "installing Rust (rustup)"
  download https://sh.rustup.rs "$DOWNLOADS_DIR/rustup-init.sh"
  sh "$DOWNLOADS_DIR/rustup-init.sh" -y --default-toolchain stable --profile minimal
fi

log "### 20_dev-toolchain: done"
