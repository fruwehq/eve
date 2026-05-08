#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg dev-toolchain

log "### dev-toolchain: build tools + language toolchains"

apt_update_once
apt_install build-essential pkg-config libssl-dev python3 python3-pip python3-venv

if ! command -v node >/dev/null 2>&1; then
  log "installing Node.js (NodeSource LTS)"
  download https://deb.nodesource.com/setup_lts.x "$DOWNLOADS_DIR/nodesource_setup_lts.sh"
  sudo -E bash "$DOWNLOADS_DIR/nodesource_setup_lts.sh"
  apt_install nodejs
fi

if ! human_run sh -lc 'command -v rustc >/dev/null 2>&1'; then
  log "installing Rust (rustup)"
  download https://sh.rustup.rs "$DOWNLOADS_DIR/rustup-init.sh"
  human_install_dir -m 0755 "$HUMAN_HOME/.cache/egame"
  sudo install -o "$HUMAN_USER_NAME" -g "$HUMAN_GROUP" -m 0755 "$DOWNLOADS_DIR/rustup-init.sh" "$HUMAN_HOME/.cache/egame/rustup-init.sh"
  human_run sh "$HUMAN_HOME/.cache/egame/rustup-init.sh" -y --default-toolchain stable --profile minimal
fi

log "### dev-toolchain: done"
