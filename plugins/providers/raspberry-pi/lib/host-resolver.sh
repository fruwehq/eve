#!/usr/bin/env bash
# Resolve hostnames with explicit host-OS dispatch.

resolve_host_ip() {
  local host="$1"
  local ip=""
  local os_name

  # If $host is already an IPv4 literal (digits and dots only), echo it back
  # without invoking the resolver. Hostnames (containing letters) fall through.
  case "$host" in
    ''|*[!0-9.]*) ;;
    *.*) printf '%s\n' "$host"; return 0 ;;
  esac

  os_name="$(uname -s)"
  case "$os_name" in
    Linux)
      if ! command -v getent >/dev/null 2>&1; then
        echo "resolve-host-ip: getent is required on Linux" >&2
        return 2
      fi
      ip=$(getent ahostsv4 "$host" 2>/dev/null | awk '{print $1; exit}')
      ;;
    Darwin)
      if ! command -v dscacheutil >/dev/null 2>&1; then
        echo "resolve-host-ip: dscacheutil is required on macOS" >&2
        return 2
      fi
      ip=$(dscacheutil -q host -a name "$host" 2>/dev/null | awk '/ip_address:/ {print $2; exit}')
      ;;
    *)
      echo "resolve-host-ip: unsupported host OS: $os_name" >&2
      return 2
      ;;
  esac

  [ -n "$ip" ] || return 1
  printf '%s\n' "$ip"
}
