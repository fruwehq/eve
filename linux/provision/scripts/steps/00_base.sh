#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

log "### 00_base: apt update + common tools"

apt_update_once
apt_install ca-certificates curl git gnupg jq lsb-release unzip

log "### 00_base: done"
