#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg vscode

if ! is_desktop; then
  log "### 24_vscode: headless OS — skipping"
  exit 0
fi

log "### 24_vscode: installing Visual Studio Code"

if command -v code >/dev/null 2>&1; then
  log "vscode already installed — skipping"
  exit 0
fi

apt_install wget gpg

wget -qO- https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor -o /usr/share/keyrings/microsoft.gpg
sudo sh -c 'echo "Types: deb
URIs: https://packages.microsoft.com/repos/code
Suites: stable
Components: main
Architectures: amd64,arm64,armhf
Signed-By: /usr/share/keyrings/microsoft.gpg" > /etc/apt/sources.list.d/vscode.sources'

sudo DEBIAN_FRONTEND=noninteractive apt-get update -y
apt_install code

log "### 24_vscode: done"
