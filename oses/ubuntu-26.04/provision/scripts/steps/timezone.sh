#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

if [ -z "${TIMEZONE:-}" ]; then
  log "### timezone: TIMEZONE not set — skipping"
  exit 0
fi

log "### timezone: setting timezone=${TIMEZONE}"
sudo timedatectl set-timezone "$TIMEZONE"
log "### timezone: done"
