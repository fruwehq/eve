#!/usr/bin/env bash
# Shared SSH helpers for per-provider plugin commands.
# Provider-agnostic.
#
# Usage:
#   . plugins/providers/_common/lib/ssh-helpers.sh
#
# Provides: eve_resolve_priv_key, eve_default_ssh_opts

eve_resolve_priv_key() {
  local key_file="${SSH_PUBLIC_KEY_FILE:-}"
  local priv
  if [ -n "$key_file" ] && [ "${key_file%.pub}" != "$key_file" ]; then
    priv="${key_file%.pub}"
  else
    priv="${SSH_PRIVATE_KEY_FILE:-}"
  fi
  [ -z "$priv" ] || priv="$(eve_normalize_path "$priv")"
  printf '%s' "$priv"
}

# eve_default_ssh_opts <known_hosts_file> [batch=0|1]
# Echoes the default SSH options. Caller appends -i, HostKeyAlias, etc.
eve_default_ssh_opts() {
  local known_hosts="$1"
  local batch="${2:-0}"
  local opts=(
    -o StrictHostKeyChecking=no
    -o UserKnownHostsFile="$known_hosts"
    -o ConnectTimeout=10
    -o ConnectionAttempts=1
    -o ServerAliveInterval=10
    -o ServerAliveCountMax=3
    -o WarnWeakCrypto=no-pq-kex
  )
  if [ "$batch" = "1" ] || [ "${EPHEMERAL_SSH_BATCH:-0}" = "1" ]; then
    opts+=(-o BatchMode=yes -o NumberOfPasswordPrompts=0)
  fi
  printf '%s\n' "${opts[@]}"
}
