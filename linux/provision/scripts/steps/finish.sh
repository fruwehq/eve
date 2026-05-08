#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

log "### finish: provisioning complete"
log "bundle packages: $(tr '\n' ' ' < "$BUNDLE_PACKAGES_FILE" 2>/dev/null || echo '(none)')"
