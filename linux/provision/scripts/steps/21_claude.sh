#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg claude

log "### 21_claude: installing Claude Code CLI"

if command -v claude >/dev/null 2>&1; then
  log "claude already installed — skipping"
  exit 0
fi

curl -fsSL https://claude.ai/install.sh | bash

log "### 21_claude: done"
