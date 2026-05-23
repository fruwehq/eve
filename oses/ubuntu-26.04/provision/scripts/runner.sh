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
STATUS_FILE="$STATE_DIR/provision-status.json"
MANIFEST_FILE="$STATE_DIR/provision-manifest.json"

export PROVISION_ROOT

mkdir -p "$STATE_DIR" "$LOGS_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "Another provisioning runner is already active." | tee -a "$LOG_FILE"
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "ERROR: jq is required for the provision status protocol." | tee -a "$LOG_FILE"
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

iso_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

read_step() {
  jq -r '.currentStep' "$STATE_FILE"
}

write_step() {
  printf '{"currentStep":%d}\n' "$1" > "$STATE_FILE"
}

validate_manifest() {
  [ -f "$MANIFEST_FILE" ] || { log "No provision manifest found — continuing with step discovery (compatibility mode)."; return 0; }
  log "Validating provision manifest..."

  local manifest_api_ver manifest_os manifest_steps_len
  manifest_api_ver=$(jq -r '.api_version' "$MANIFEST_FILE")
  if [ "$manifest_api_ver" != "1" ]; then
    log "ERROR: manifest api_version is '$manifest_api_ver', expected '1'"
    return 1
  fi

  manifest_os=$(jq -r '.os_family' "$MANIFEST_FILE")
  if [ "$manifest_os" != "ubuntu" ]; then
    log "ERROR: manifest os_family is '$manifest_os', expected 'ubuntu'"
    return 1
  fi

  manifest_steps_len=$(jq '.steps | length' "$MANIFEST_FILE")
  local actual_count
  actual_count=$(find "$STEPS_DIR" -maxdepth 1 -type f -name '*.sh' ! -name '._*' | wc -l | tr -d ' ')
  if [ "$manifest_steps_len" -ne "$actual_count" ]; then
    log "ERROR: manifest declares $manifest_steps_len steps but $actual_count step files found"
    return 1
  fi

  local i=0
  while [ "$i" -lt "$manifest_steps_len" ]; do
    local expected_name expected_hash actual_hash step_path expected_order
    expected_name=$(jq -r ".steps[$i].name" "$MANIFEST_FILE")
    expected_order=$(jq -r ".steps[$i].order" "$MANIFEST_FILE")
    if [ "$expected_order" != "$i" ]; then
      log "ERROR: manifest step[$i] has order $expected_order, expected $i"
      return 1
    fi
    local actual_name
    actual_name="$(basename "${STEPS[$i]}")"
    if [ "$expected_name" != "$actual_name" ]; then
      log "ERROR: manifest step[$i] is '$expected_name', but execution step is '$actual_name'"
      return 1
    fi
    step_path="$STEPS_DIR/$expected_name"
    if [ ! -f "$step_path" ]; then
      log "ERROR: manifest step '$expected_name' (index $i) not found in $STEPS_DIR"
      return 1
    fi
    expected_hash=$(jq -r ".steps[$i].sha256" "$MANIFEST_FILE")
    actual_hash=$(sha256sum "$step_path" | awk '{print $1}')
    if [ "$expected_hash" != "$actual_hash" ]; then
      log "ERROR: manifest hash mismatch for step '$expected_name' (expected $expected_hash, got $actual_hash)"
      return 1
    fi
    i=$((i + 1))
  done

  log "Manifest validated: $manifest_steps_len steps, all hashes match."
  return 0
}

ensure_status_file() {
  if [ -f "$STATUS_FILE" ]; then
    local existing_api existing_status existing_count expected_count
    existing_api=$(jq -r '.api_version // "missing"' "$STATUS_FILE")
    if [ "$existing_api" != "1" ]; then
      log "ERROR: existing status file has api_version '$existing_api', expected '1'"
      return 1
    fi
    existing_status=$(jq -r '.status // "missing"' "$STATUS_FILE")
    case "$existing_status" in
      running|done|failed) ;;
      *) log "ERROR: existing status file has invalid status '$existing_status'"; return 1 ;;
    esac
    existing_count=$(jq '.steps | length' "$STATUS_FILE")
    expected_count=${#STEPS[@]}
    if [ "$existing_count" -ne "$expected_count" ]; then
      log "ERROR: existing status file has $existing_count steps, expected $expected_count"
      return 1
    fi
    local i=0
    while [ "$i" -lt "$expected_count" ]; do
      local existing_name expected_name
      existing_name=$(jq -r ".steps[$i].step // \"\"" "$STATUS_FILE")
      expected_name="$(basename "${STEPS[$i]}")"
      if [ "$existing_name" != "$expected_name" ]; then
        log "ERROR: existing status file step[$i] is '$existing_name', expected '$expected_name'"
        return 1
      fi
      i=$((i + 1))
    done
    local tmp
    tmp=$(mktemp)
    jq \
      --arg ts "$(iso_now)" \
      '.status = "running" | .finished_at = null' "$STATUS_FILE" > "$tmp" && mv "$tmp" "$STATUS_FILE"
    log "Resuming provisioning — preserved prior step status from existing status file."
  else
    local steps_json="[]"
    for step in "${STEPS[@]}"; do
      steps_json=$(printf '%s' "$steps_json" | jq \
        --arg name "$(basename "$step")" \
        '. += [{"step": $name, "phase": "pending", "started_at": null, "ended_at": null, "exit_code": null}]')
    done
    jq -n \
      --argjson steps "$steps_json" \
      --arg started "$(iso_now)" \
      '{api_version: 1, os_family: "ubuntu", started_at: $started, finished_at: null, status: "running", steps: $steps}' \
      > "$STATUS_FILE"
  fi
}

update_step_status() {
  local step_index="$1"
  local phase="$2"
  local exit_code="${3:-null}"
  local timestamp
  timestamp="$(iso_now)"

  if [ ! -f "$STATUS_FILE" ]; then
    log "ERROR: status file missing during update"
    return 1
  fi

  local tmp
  tmp=$(mktemp)
  jq \
    --arg idx "$step_index" \
    --arg phase "$phase" \
    --arg ts "$timestamp" \
    --argjson ec "$exit_code" \
    '(.steps[($idx|tonumber)] // {}) |= (
      .phase = $phase |
      if $phase == "running" then .started_at = $ts else . end |
      if ($phase == "succeeded" or $phase == "failed") then .ended_at = $ts else . end |
      .exit_code = $ec
    )' "$STATUS_FILE" > "$tmp" && mv "$tmp" "$STATUS_FILE"
}

finish_status() {
  local final_status="$1"
  if [ ! -f "$STATUS_FILE" ]; then
    log "ERROR: status file missing during finish"
    return 1
  fi
  local tmp
  tmp=$(mktemp)
  jq \
    --arg status "$final_status" \
    --arg ts "$(iso_now)" \
    '.status = $status | .finished_at = $ts' "$STATUS_FILE" > "$tmp" && mv "$tmp" "$STATUS_FILE"
}

[ -d "$STEPS_DIR" ] || { log "ERROR: steps dir missing: $STEPS_DIR"; exit 1; }

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

ensure_status_file

if ! validate_manifest; then
  finish_status "failed"
  exit 1
fi

while : ; do
  current=$(read_step)
  [ -n "$current" ] || current=0

  if [ "$current" -ge "$TOTAL" ]; then
    finish_status "done"
    log "Provisioning complete."
    exit 0
  fi

  step="${STEPS[$current]}"
  log "Running step [$current/$((TOTAL - 1))] $(basename "$step")"
  update_step_status "$current" "running"

  set +e
  line_buffered /usr/bin/env bash "$step" 2>&1 | line_buffered tee -a "$LOG_FILE"
  step_exit=${PIPESTATUS[0]}
  set -e

  if [ "$step_exit" -ne 0 ]; then
    update_step_status "$current" "failed" "$step_exit"
    finish_status "failed"
    log "ERROR: step $(basename "$step") failed (exit $step_exit)"
    exit 1
  fi

  update_step_status "$current" "succeeded" 0
  write_step "$((current + 1))"

  if [ -f "$REBOOT_FLAG" ]; then
    rm -f "$REBOOT_FLAG"
    log "Reboot requested. Rebooting..."
    sudo systemctl reboot
    exit 0
  fi
done
