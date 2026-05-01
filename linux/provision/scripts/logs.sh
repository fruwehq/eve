#!/usr/bin/env bash
# Dump all provisioning log files. Invoked remotely by `make profile.logs`.
set -euo pipefail

PROVISION_ROOT="${PROVISION_ROOT:-$HOME/provision}"
LOGS_DIR="$PROVISION_ROOT/logs"

if [ ! -d "$LOGS_DIR" ]; then
  echo "No logs directory found."
  exit 0
fi

for f in "$LOGS_DIR"/*; do
  [ -f "$f" ] || continue
  printf '==== %s ====\n' "$(basename "$f")"
  cat "$f"
done
