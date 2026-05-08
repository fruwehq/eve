#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg opencode

log "### opencode: installing OpenCode CLI"

if human_run sh -lc 'command -v opencode >/dev/null 2>&1'; then
  log "opencode already installed — skipping"
  exit 0
fi

human_install_dir -m 0755 "$HUMAN_HOME/.cache" "$HUMAN_HOME/.config" "$HUMAN_HOME/.local" "$HUMAN_HOME/.local/bin"
human_run sh -lc 'curl -fsSL https://opencode.ai/install | bash'

log "### opencode: done"
