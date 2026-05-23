#!/usr/bin/env bash
# TrueNAS-specific host-SSH helpers used by status/start/stop/ip.
# Sourced by plugins/providers/truenas/commands/*.

# Caller must have sourced profile-env.sh first (for eve_normalize_path).

truenas_ssh_opts() {
  TRUENAS_SSH_USER_RESOLVED="${TRUENAS_SSH_USER:-terraform}"
  TRUENAS_SSH_OPTS=(-o StrictHostKeyChecking=no -o IdentitiesOnly=yes)
  if [ -n "${TRUENAS_SSH_PRIVATE_KEY_FILE:-}" ]; then
    TRUENAS_SSH_KEY="$(eve_normalize_path "${TRUENAS_SSH_PRIVATE_KEY_FILE}")"
    TRUENAS_SSH_OPTS+=(-i "$TRUENAS_SSH_KEY")
  fi
  if [ -n "${TRUENAS_SSH_PORT:-}" ] && [ "${TRUENAS_SSH_PORT}" != "22" ]; then
    TRUENAS_SSH_OPTS+=(-p "$TRUENAS_SSH_PORT")
  fi
}

# truenas_vm_state <vm_id>
# Echoes the live VM state via midclt over SSH; empty if unreachable.
truenas_vm_state() {
  local vm_id="$1" output
  truenas_ssh_opts
  # shellcheck disable=SC2029
  output=$(ssh "${TRUENAS_SSH_OPTS[@]}" "${TRUENAS_SSH_USER_RESOLVED}@${TRUENAS_HOST}" \
    "sudo midclt call vm.query '[[\"id\",\"=\",$vm_id]]'" 2>/dev/null) || return 1
  printf '%s\n' "$output" | jq -r '.[0].status.state // .[0].state // empty' 2>/dev/null
}

# truenas_control_reachable
# Prints a Control: line and returns 0 if the NAS SSH port answers.
truenas_control_reachable() {
  local host port
  host="${TRUENAS_HOST:-$(eve_resolved_value TRUENAS_HOST)}"
  port="${TRUENAS_SSH_PORT:-$(eve_resolved_value TRUENAS_SSH_PORT)}"
  port="${port:-22}"

  if [ -z "$host" ]; then
    printf '%-15s %s\n' "Control:" "unreachable (missing TRUENAS_HOST)"
    return 1
  fi

  if command -v nc >/dev/null 2>&1; then
    if nc -z -w 2 "$host" "$port" >/dev/null 2>&1; then
      printf '%-15s %s\n' "Control:" "reachable (TrueNAS SSH $host:$port)"
      return 0
    fi
    printf '%-15s %s\n' "Control:" "unreachable (TrueNAS SSH $host:$port)"
    return 1
  fi

  printf '%-15s %s\n' "Control:" "unknown (nc not found; TrueNAS SSH $host:$port)"
  return 0
}
