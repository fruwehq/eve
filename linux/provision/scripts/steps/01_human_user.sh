#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

[ -n "${VM_USER_NAME:-}" ] || {
  log "### 01_human_user: no VM_USER_NAME configured"
  exit 0
}

case "$VM_USER_NAME" in
  *[!a-zA-Z0-9._-]*)
    log "### 01_human_user: invalid VM_USER_NAME=$VM_USER_NAME"
    exit 2
    ;;
esac

if [ "$VM_USER_NAME" = "$PROVISION_USER_NAME" ]; then
  log "### 01_human_user: VM user is provisioning user ($VM_USER_NAME)"
  exit 0
fi

if id "$VM_USER_NAME" >/dev/null 2>&1; then
  log "### 01_human_user: user exists: $VM_USER_NAME"
else
  log "### 01_human_user: creating user: $VM_USER_NAME"
  sudo useradd --create-home --shell /bin/bash --groups sudo "$VM_USER_NAME"
fi

if [ -n "${VM_USER_PASSWORD:-}" ]; then
  log "### 01_human_user: setting password for $VM_USER_NAME"
  printf '%s:%s\n' "$VM_USER_NAME" "$VM_USER_PASSWORD" | sudo chpasswd
else
  log "### 01_human_user: locking password for $VM_USER_NAME"
  sudo passwd -l "$VM_USER_NAME" >/dev/null
fi

if [ -r "$HOME/.ssh/authorized_keys" ]; then
  target_home=$(getent passwd "$VM_USER_NAME" | awk -F: '{print $6}')
  target_group=$(id -gn "$VM_USER_NAME")
  sudo install -d -o "$VM_USER_NAME" -g "$target_group" -m 0700 "$target_home/.ssh"
  sudo install -o "$VM_USER_NAME" -g "$target_group" -m 0600 "$HOME/.ssh/authorized_keys" "$target_home/.ssh/authorized_keys"
fi

log "### 01_human_user: done"
