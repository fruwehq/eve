#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg opencode

log "### 22_opencode: installing OpenCode CLI"

if human_run sh -lc 'command -v opencode >/dev/null 2>&1'; then
  log "opencode already installed — skipping"
  exit 0
fi

human_run sh -lc 'curl -fsSL https://opencode.ai/install | bash'

log "### 22_opencode: done"
