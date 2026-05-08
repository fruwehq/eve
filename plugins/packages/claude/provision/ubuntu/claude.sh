#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg claude

log "### claude: installing Claude Code CLI"

if human_run sh -lc 'command -v claude >/dev/null 2>&1'; then
  log "claude already installed — skipping"
  exit 0
fi

human_install_dir -m 0755 "$HUMAN_HOME/.cache" "$HUMAN_HOME/.cache/claude"
human_install_dir -m 0755 "$HUMAN_HOME/.config" "$HUMAN_HOME/.local" "$HUMAN_HOME/.local/bin"
if ! human_run sh -lc 'curl -fsSL https://claude.ai/install.sh | bash'; then
  log "Claude native installer failed; trying npm fallback"
  if ! command -v npm >/dev/null 2>&1; then
    log "npm not found - ensure dev-toolchain bundle is included before claude"
    exit 1
  fi
  sudo npm install -g @anthropic-ai/claude-code
fi

if ! human_run sh -lc 'command -v claude >/dev/null 2>&1 || [ -x "$HOME/.local/bin/claude" ]'; then
  log "claude command not found after installation"
  exit 1
fi

log "### claude: done"
