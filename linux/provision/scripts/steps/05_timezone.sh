#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

if [ -z "${TIMEZONE:-}" ]; then
  log "### 05_timezone: TIMEZONE not set — skipping"
  exit 0
fi

log "### 05_timezone: setting timezone=${TIMEZONE}"
sudo timedatectl set-timezone "$TIMEZONE"
log "### 05_timezone: done"
