#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

log "### 00_base: apt update + common tools"

if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
fi

if [ -f /etc/apt/sources.list.d/ubuntu-updates.sources ] && \
  ! awk '/^URIs:/ && $2 ~ /^https?:/ {found=1} END {exit found ? 0 : 1}' /etc/apt/sources.list.d/ubuntu-updates.sources; then
  log "removing malformed Ubuntu updates apt source"
  sudo rm -f /etc/apt/sources.list.d/ubuntu-updates.sources
fi

if [ -n "${VERSION_CODENAME:-}" ] && ! grep -Rqs "\\b${VERSION_CODENAME}-updates\\b" /etc/apt/sources.list /etc/apt/sources.list.d; then
  log "adding Ubuntu ${VERSION_CODENAME}-updates apt source"
  APT_URI=""
  if [ -r /etc/apt/sources.list.d/ubuntu.sources ]; then
    APT_URI=$(awk '/^URIs:/ {print $2; exit}' /etc/apt/sources.list.d/ubuntu.sources)
  fi
  if [ -z "$APT_URI" ]; then
    APT_URI=$(awk '$1 == "deb" && $2 ~ /^https?:/ {print $2; exit}' /etc/apt/sources.list /etc/apt/sources.list.d/*.list 2>/dev/null)
  fi
  APT_URI="${APT_URI:-http://ports.ubuntu.com/ubuntu-ports/}"
  sudo tee /etc/apt/sources.list.d/ubuntu-updates.sources >/dev/null <<EOF
Types: deb
URIs: $APT_URI
Suites: ${VERSION_CODENAME}-updates
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF
  rm -f "$STATE_DIR/apt_updated"
fi

apt_update_once
apt_install autocutsel bmon ca-certificates curl git glances gnupg iftop jq locales lsb-release nload unzip xclip xsel

if ! locale -a 2>/dev/null | grep -Fixq "en_US.utf8"; then
  log "### 00_base: generating en_US.UTF-8 locale"
  sudo sed -i 's/^# *\(en_US.UTF-8 UTF-8\)/\1/' /etc/locale.gen
  sudo locale-gen en_US.UTF-8
fi

sudo update-locale LANG=en_US.UTF-8

log "### 00_base: done"
