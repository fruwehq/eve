#!/usr/bin/env bash
# runner.sh — executes numbered step scripts, resumable via state.json.
# On reboot.flag, requests a reboot and exits so systemd can resume us.

set -euo pipefail

PROVISION_ROOT="${PROVISION_ROOT:-$HOME/provision}"
SCRIPTS_DIR="$PROVISION_ROOT/scripts"
STEPS_DIR="$SCRIPTS_DIR/steps"
STATE_DIR="$PROVISION_ROOT/state"
LOGS_DIR="$PROVISION_ROOT/logs"
STATE_FILE="$STATE_DIR/state.json"
REBOOT_FLAG="$STATE_DIR/reboot.flag"
LOG_FILE="$LOGS_DIR/provision.log"

export PROVISION_ROOT

mkdir -p "$STATE_DIR" "$LOGS_DIR"

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

read_step() {
  if command -v jq >/dev/null 2>&1; then
    jq -r '.currentStep' "$STATE_FILE"
  else
    sed -n 's/.*"currentStep"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' "$STATE_FILE" | head -n1
  fi
}

write_step() {
  printf '{"currentStep":%d}\n' "$1" > "$STATE_FILE"
}

[ -d "$STEPS_DIR" ] || { log "ERROR: steps dir missing: $STEPS_DIR"; exit 1; }

# Load environment snapshot written by the uploader (OS_UI_MODE, PROFILE_NAME, ...).
# shellcheck disable=SC1091
[ -f "$STATE_DIR/env" ] && . "$STATE_DIR/env"

mapfile -t STEPS < <(find "$STEPS_DIR" -maxdepth 1 -type f -name '*.sh' | sort)
TOTAL=${#STEPS[@]}

while : ; do
  current=$(read_step)
  [ -n "$current" ] || current=0

  if [ "$current" -ge "$TOTAL" ]; then
    log "Provisioning complete."
    exit 0
  fi

  step="${STEPS[$current]}"
  log "Running step [$current/$((TOTAL - 1))] $(basename "$step")"

  if ! /usr/bin/env bash "$step" 2>&1 | tee -a "$LOG_FILE"; then
    log "ERROR: step $(basename "$step") failed"
    exit 1
  fi

  write_step "$((current + 1))"

  if [ -f "$REBOOT_FLAG" ]; then
    rm -f "$REBOOT_FLAG"
    log "Reboot requested. Rebooting..."
    sudo systemctl reboot
    exit 0
  fi
done
