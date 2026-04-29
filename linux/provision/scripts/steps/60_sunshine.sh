#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg sunshine

if ! is_desktop; then
  log "### 60_sunshine: headless OS — skipping"
  exit 0
fi

log "### 60_sunshine: installing LizardByte Sunshine"

if ! command -v sunshine >/dev/null 2>&1; then
  arch=$(dpkg --print-architecture)
  # shellcheck disable=SC1091
  codename=$(. /etc/os-release && echo "$VERSION_CODENAME")
  case "$arch-$codename" in
    amd64-noble|amd64-resolute)    asset="sunshine-ubuntu-24.04-amd64.deb" ;;
    arm64-noble|arm64-resolute)    asset="sunshine-ubuntu-24.04-arm64.deb" ;;
    amd64-jammy)                   asset="sunshine-ubuntu-22.04-amd64.deb" ;;
    arm64-jammy)                   asset="sunshine-ubuntu-22.04-arm64.deb" ;;
    *) log "no known Sunshine package for $arch/$codename"; exit 1 ;;
  esac

  : "${SUNSHINE_VERSION:?SUNSHINE_VERSION must be set in .env}"
  url="https://github.com/LizardByte/Sunshine/releases/download/v${SUNSHINE_VERSION}/${asset}"

  deb="$DOWNLOADS_DIR/$asset"
  download "$url" "$deb"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$deb"

  # The noble deb is built against Ubuntu 24.04 libs. On newer releases the
  # sonames have bumped — create compatibility symlinks so the binary can load.
  # shellcheck disable=SC1091
  codename=$(. /etc/os-release && echo "$VERSION_CODENAME")
  if [ "$codename" != "noble" ] && [ "$codename" != "jammy" ]; then
    log "### 60_sunshine: patching shared-library sonames for $codename"
    sudo ln -sf libminiupnpc.so.21 /usr/lib/x86_64-linux-gnu/libminiupnpc.so.17 2>/dev/null || true
    sudo ln -sf libicuuc.so.78 /usr/lib/x86_64-linux-gnu/libicuuc.so.74 2>/dev/null || true
    sudo ldconfig
  fi
else
  log "sunshine already installed — skipping install"
fi

# Configure web UI to be reachable from outside localhost. Without this, the
# host (or vagrant port-forwarder) can hit the port but Sunshine returns 401/403
# because the web UI is locked to local-origin requests by default.
log "### 60_sunshine: configuring web UI"
mkdir -p "$HOME/.config/sunshine"
SUN_CONF="$HOME/.config/sunshine/sunshine.conf"
touch "$SUN_CONF"

set_sunshine_config() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}[[:space:]]*=" "$SUN_CONF"; then
    sed -i "s|^${key}[[:space:]]*=.*|${key} = ${value}|" "$SUN_CONF"
  else
    printf '%s = %s\n' "$key" "$value" >> "$SUN_CONF"
  fi
}

unset_sunshine_config() {
  local key="$1"
  sed -i "/^${key}[[:space:]]*=/d" "$SUN_CONF" 2>/dev/null || true
}

set_sunshine_config origin_web_ui_allowed wan
unset_sunshine_config fps
unset_sunshine_config resolutions

if [ "${PROVIDER:-}" = "raspberry-pi" ]; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y kmod
  sudo groupadd --system uinput 2>/dev/null || true
  sudo usermod -aG input "$USER"
  sudo usermod -aG uinput "$USER"
  echo uinput | sudo tee /etc/modules-load.d/egame-uinput.conf >/dev/null
  sudo modprobe uinput 2>/dev/null || true
  sudo tee /etc/udev/rules.d/70-egame-uinput.rules >/dev/null <<'EOF'
KERNEL=="uinput", SUBSYSTEM=="misc", OPTIONS+="static_node=uinput", MODE="0660", GROUP="uinput", TAG+="uaccess"
EOF
  sudo udevadm control --reload-rules 2>/dev/null || true
  sudo udevadm trigger /dev/uinput 2>/dev/null || true
  sudo chgrp uinput /dev/uinput 2>/dev/null || true
  sudo chmod 0660 /dev/uinput 2>/dev/null || true

  set_sunshine_config output_name 0
  set_sunshine_config encoder software
  set_sunshine_config min_threads 1
  set_sunshine_config hevc_mode 1
  set_sunshine_config av1_mode 1
  set_sunshine_config sw_preset ultrafast
  set_sunshine_config sw_tune zerolatency
  set_sunshine_config max_bitrate "${SUNSHINE_MAX_BITRATE_KBPS:-3000}"
fi

# Set Sunshine web UI credentials (matches Windows step 10's behavior).
if [ -n "${EPHEMERAL_SUNSHINE_PASSWORD:-}" ]; then
  log "### 60_sunshine: setting web UI credentials"
  sunshine "$SUN_CONF" --creds sunshine "$EPHEMERAL_SUNSHINE_PASSWORD" || \
    log "### 60_sunshine: warn: failed to set credentials (will retry on next run)"
else
  log "### 60_sunshine: EPHEMERAL_SUNSHINE_PASSWORD not set — skipping creds"
fi

# Sunshine must have exactly one owner. The package-provided systemd user unit
# is persistent with linger enabled; XFCE autostart creates a second generated
# app-sunshine@autostart.service and can race or duplicate CPU-heavy encoders.
rm -f "$HOME/.config/autostart/sunshine.desktop"

if [ "${PROVIDER:-}" = "raspberry-pi" ]; then
  cat > "$HOME/.config/sunshine/apps.json" <<'EOF'
{
  "env": {
    "PATH": "$(PATH):$(HOME)/.local/bin"
  },
  "apps": [
    {
      "name": "Desktop",
      "image-path": "desktop.png"
    }
  ]
}
EOF
fi

XDG_RUNTIME_DIR="/run/user/$(id -u)"
export XDG_RUNTIME_DIR
SUN_DISPLAY="${SUNSHINE_DISPLAY:-:0}"
SUN_XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

sudo loginctl enable-linger "$USER"
systemctl --user enable sunshine 2>/dev/null || true
systemctl --user add-wants default.target sunshine.service 2>/dev/null || true

sunshine_display_ready() {
  DISPLAY="$SUN_DISPLAY" XAUTHORITY="$SUN_XAUTHORITY" xrandr --query >/dev/null 2>&1
}

sunshine_kms_ready() {
  local connector="${RASPBERRY_PI_HDMI_CONNECTOR:-HDMI-A-1}"
  [ "${PROVIDER:-}" = "raspberry-pi" ] || return 1
  for status in /sys/class/drm/card*-"$connector"/status; do
    [ -e "$status" ] || continue
    grep -qx connected "$status" && return 0
  done
  return 1
}

start_sunshine_with_display() {
  export DISPLAY="$SUN_DISPLAY"
  export XAUTHORITY="$SUN_XAUTHORITY"
  [ -x "$HOME/.local/bin/egame-set-display-mode" ] && "$HOME/.local/bin/egame-set-display-mode" || true
  systemctl --user import-environment DISPLAY XAUTHORITY XDG_RUNTIME_DIR 2>/dev/null || true
  systemctl --user start sunshine 2>/dev/null || \
    setsid nohup sunshine "$SUN_CONF" >>"$LOGS_DIR/sunshine.log" 2>&1 < /dev/null &
}

if systemctl --user is-active sunshine >/dev/null 2>&1; then
  log "### 60_sunshine: restarting sunshine to reload config"
  export DISPLAY="$SUN_DISPLAY"
  export XAUTHORITY="$SUN_XAUTHORITY"
  [ -x "$HOME/.local/bin/egame-set-display-mode" ] && "$HOME/.local/bin/egame-set-display-mode" || true
  systemctl --user restart sunshine 2>/dev/null || true
elif [ -d "$XDG_RUNTIME_DIR" ] && { sunshine_display_ready || sunshine_kms_ready; }; then
  log "### 60_sunshine: starting sunshine on display $SUN_DISPLAY"
  start_sunshine_with_display
else
  log "### 60_sunshine: no usable user display yet — sunshine will start at next autologin"
fi

log "### 60_sunshine: done"
