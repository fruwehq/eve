#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

[ -n "${VM_USER_NAME:-}" ] || {
  log "### human-user: no VM_USER_NAME configured"
  exit 0
}

case "$HUMAN_USER_NAME" in
  *[!a-zA-Z0-9._-]*)
    log "### human-user: invalid HUMAN_USER_NAME=$HUMAN_USER_NAME"
    exit 2
    ;;
esac

if id "$HUMAN_USER_NAME" >/dev/null 2>&1; then
  log "### human-user: user exists: $HUMAN_USER_NAME"
else
  log "### human-user: creating user: $HUMAN_USER_NAME"
  sudo useradd --create-home --shell /bin/bash --groups sudo "$HUMAN_USER_NAME"
fi

if [ -n "${VM_USER_PASSWORD:-}" ]; then
  log "### human-user: setting password for $HUMAN_USER_NAME"
  printf '%s:%s\n' "$HUMAN_USER_NAME" "$VM_USER_PASSWORD" | sudo chpasswd
else
  log "### human-user: locking password for $HUMAN_USER_NAME"
  sudo passwd -l "$HUMAN_USER_NAME" >/dev/null
fi

if [ "$HUMAN_USER_NAME" != "$PROVISION_USER_NAME" ] && [ -r "$HOME/.ssh/authorized_keys" ]; then
  target_home=$(getent passwd "$HUMAN_USER_NAME" | awk -F: '{print $6}')
  target_group=$(id -gn "$HUMAN_USER_NAME")
  sudo install -d -o "$HUMAN_USER_NAME" -g "$target_group" -m 0700 "$target_home/.ssh"
  sudo install -o "$HUMAN_USER_NAME" -g "$target_group" -m 0600 "$HOME/.ssh/authorized_keys" "$target_home/.ssh/authorized_keys"
fi

log "### human-user: done"
