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

claude_present() {
  human_run sh -lc 'command -v claude >/dev/null 2>&1 || [ -x "$HOME/.local/bin/claude" ]'
}

# Try the native installer first. On arm64 Linux it currently prints
# "Installation complete!" without actually delivering a binary, so we
# verify with a real claude_present check after either path.
human_run sh -lc 'curl -fsSL https://claude.ai/install.sh | bash' || true

if ! claude_present; then
  log "Claude native installer did not produce a binary; trying npm fallback"
  if ! command -v npm >/dev/null 2>&1; then
    log "npm not found - select dev-toolchain together with claude so the fallback can run"
    exit 1
  fi
  sudo npm install -g @anthropic-ai/claude-code
fi

if ! claude_present; then
  log "claude command not found after installation"
  exit 1
fi

log "### claude: done"
