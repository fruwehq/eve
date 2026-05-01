#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg goose

log "### 40_goose: installing Block's goose CLI"

if command -v goose >/dev/null 2>&1; then
  log "goose already installed — skipping"
  exit 0
fi

# Block/goose ships a shell installer at the canonical URL.
curl -fsSL https://github.com/block/goose/releases/download/stable/download_cli.sh \
  | CONFIGURE=false bash

log "### 40_goose: done"
