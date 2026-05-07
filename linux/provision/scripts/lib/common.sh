#!/usr/bin/env bash
# Shared helpers for linux provisioning steps.
# Sourced by each step script via:  . "$PROVISION_ROOT/scripts/lib/common.sh"

set -euo pipefail

PROVISION_ROOT="${PROVISION_ROOT:-$HOME/provision}"
STATE_DIR="$PROVISION_ROOT/state"
LOGS_DIR="$PROVISION_ROOT/logs"
DOWNLOADS_DIR="$PROVISION_ROOT/downloads"
REBOOT_FLAG="$STATE_DIR/reboot.flag"
BUNDLE_PACKAGES_FILE="$STATE_DIR/bundle_packages"

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

mkdir -p "$STATE_DIR" "$LOGS_DIR" "$DOWNLOADS_DIR"

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

has_pkg() {
  [ -f "$BUNDLE_PACKAGES_FILE" ] || return 1
  grep -Fqx "$1" "$BUNDLE_PACKAGES_FILE"
}

skip_unless_pkg() {
  if ! has_pkg "$1"; then
    log "skip: package '$1' not in bundle"
    exit 0
  fi
}

apt_wait() {
  if command -v cloud-init >/dev/null 2>&1; then
    timeout 600 cloud-init status --wait >/dev/null 2>&1 || true
  fi

  local waited=0
  local max_wait=600
  while sudo fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock >/dev/null 2>&1; do
    if [ "$waited" -eq 0 ]; then
      log "waiting for apt/dpkg lock"
    fi
    if [ "$waited" -ge "$max_wait" ]; then
      log "apt/dpkg lock still held after ${max_wait}s"
      return 1
    fi
    sleep 5
    waited=$((waited + 5))
  done
}

apt_install() {
  apt_wait
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@"
}

apt_update_once() {
  local stamp="$STATE_DIR/apt_updated"
  [ -f "$stamp" ] && return 0
  apt_wait
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -y
  touch "$stamp"
}

download() {
  local url="$1"
  local out="$2"
  [ -f "$out" ] && { log "already downloaded: $out"; return 0; }
  mkdir -p "$(dirname "$out")"
  curl -fsSL --retry 8 --retry-delay 3 --retry-all-errors --connect-timeout 20 -o "$out" "$url"
}

request_reboot() {
  touch "$REBOOT_FLAG"
  log "reboot requested"
}
