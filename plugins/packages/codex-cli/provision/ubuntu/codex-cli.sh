#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg codex-cli

log "### codex-cli: installing @openai/codex"

if ! command -v npm >/dev/null 2>&1; then
  log "npm not found — ensure dev-toolchain bundle is included before codex-cli"
  exit 1
fi

if command -v codex >/dev/null 2>&1; then
  log "codex already installed — skipping"
  exit 0
fi

sudo npm install -g @openai/codex

log "### codex-cli: done"
