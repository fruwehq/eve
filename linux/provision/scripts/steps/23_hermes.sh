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

curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

log "### 23_hermes: done"
