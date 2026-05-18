#!/usr/bin/env bash
# runner.sh — executes provision step scripts, resumable via state.json.
# On reboot.flag, requests a reboot and exits so systemd can resume us.

set -euo pipefail

PROVISION_ROOT="${PROVISION_ROOT:-$HOME/provision}"
SCRIPTS_DIR="$PROVISION_ROOT/scripts"
STEPS_DIR="$SCRIPTS_DIR/steps"
STATE_DIR="$PROVISION_ROOT/state"
LOGS_DIR="$PROVISION_ROOT/logs"
STATE_FILE="$STATE_DIR/state.json"
STEPS_FILE="$STATE_DIR/steps.list"
REBOOT_FLAG="$STATE_DIR/reboot.flag"
LOG_FILE="$LOGS_DIR/provision.log"
LOCK_FILE="$STATE_DIR/runner.lock"

export PROVISION_ROOT

mkdir -p "$STATE_DIR" "$LOGS_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "Another provisioning runner is already active." | tee -a "$LOG_FILE"
  exit 1
fi

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

line_buffered() {
  if command -v stdbuf >/dev/null 2>&1; then
    stdbuf -oL -eL "$@"
  else
    "$@"
  fi
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

# Load environment snapshot written by the uploader (PROFILE_NAME, package env, ...).
# shellcheck disable=SC1091
[ -f "$STATE_DIR/env" ] && . "$STATE_DIR/env"

if [ -f "$STEPS_FILE" ]; then
  mapfile -t STEP_NAMES < <(sed '/^[[:space:]]*$/d' "$STEPS_FILE")
  STEPS=()
  for step_name in "${STEP_NAMES[@]}"; do
    step="$STEPS_DIR/$step_name"
    [ -f "$step" ] || { log "ERROR: ordered step missing: $step"; exit 1; }
    STEPS+=("$step")
  done
else
  mapfile -t STEPS < <(find "$STEPS_DIR" -maxdepth 1 -type f -name '*.sh' ! -name '._*' | sort)
fi
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

  if ! line_buffered /usr/bin/env bash "$step" 2>&1 | line_buffered tee -a "$LOG_FILE"; then
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
