#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg hermes

log "### 23_hermes: installing Hermes agent"

if command -v hermes >/dev/null 2>&1; then
  log "hermes already installed — skipping"
  exit 0
fi

HERMES_VERSION="${HERMES_VERSION:-}"

apt_update_once
apt_install curl python3 python3-venv

local_arch="$(dpkg --print-architecture)"
if [[ "$local_arch" == "arm64" ]]; then
  log "detected arm64 — Hermes arm64 support is via Termux-compatible install"
fi

if [[ -n "$HERMES_VERSION" ]]; then
  log "pinning Hermes version: $HERMES_VERSION"
  curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh \
    | HERMES_VERSION="$HERMES_VERSION" bash
else
  curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
fi

if ! command -v hermes >/dev/null 2>&1; then
  log "ERROR: hermes not found after install"
  exit 1
fi

installed_version="$(hermes --version 2>/dev/null || echo "unknown")"
log "### 23_hermes: done (version: $installed_version)"
