#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg sunshine

log "### 60_sunshine: installing LizardByte Sunshine"

install_sunshine_compat_libs() {
  # The noble deb is built against Ubuntu 24.04 libs. On 26.04 (resolute) the
  # ICU soname has bumped and symbol-versioned ICU 74 symbols are required.
  # Install the real Noble runtime library rather than symlinking ICU 78, which
  # loads but fails at runtime with missing UCNV_*_74 symbols.
  # shellcheck disable=SC1091
  codename=$(. /etc/os-release && echo "$VERSION_CODENAME")
  if [ "$codename" = "noble" ] || [ "$codename" = "jammy" ]; then
    return
  fi

  log "### 60_sunshine: installing Noble compatibility libraries for $codename"
  case "$(dpkg --print-architecture)" in
    amd64) multiarch="x86_64-linux-gnu" ;;
    arm64) multiarch="aarch64-linux-gnu" ;;
    armhf) multiarch="arm-linux-gnueabihf" ;;
    *) multiarch="" ;;
  esac
  if [ -z "$multiarch" ]; then
    log "### 60_sunshine: warn: no known multiarch lib dir for $(dpkg --print-architecture)"
  fi
  lib_dir="/usr/lib/$multiarch"
  case "$(dpkg --print-architecture)" in
    amd64)
      icu_deb="libicu74_74.2-1ubuntu3.1_$(dpkg --print-architecture).deb"
      download "https://archive.ubuntu.com/ubuntu/pool/main/i/icu/$icu_deb" "$DOWNLOADS_DIR/$icu_deb"
      sudo rm -f "$lib_dir/libicuuc.so.74" "$lib_dir/libicui18n.so.74" "$lib_dir/libicudata.so.74" 2>/dev/null || true
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$DOWNLOADS_DIR/$icu_deb"
      ;;
    arm64)
      icu_deb="libicu74_74.2-1ubuntu3.1_$(dpkg --print-architecture).deb"
      download "https://ports.ubuntu.com/ubuntu-ports/pool/main/i/icu/$icu_deb" "$DOWNLOADS_DIR/$icu_deb"
      sudo rm -f "$lib_dir/libicuuc.so.74" "$lib_dir/libicui18n.so.74" "$lib_dir/libicudata.so.74" 2>/dev/null || true
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$DOWNLOADS_DIR/$icu_deb"
      ;;
    *)
      log "### 60_sunshine: warn: no libicu74 compatibility package configured for $(dpkg --print-architecture)"
      ;;
  esac
  if [ -n "$multiarch" ] && [ -e "$lib_dir/libminiupnpc.so.21" ]; then
    sudo ln -sf libminiupnpc.so.21 "$lib_dir/libminiupnpc.so.17"
  fi
  sudo ldconfig
}

if ! command -v sunshine >/dev/null 2>&1; then
  arch=$(dpkg --print-architecture)
  # shellcheck disable=SC1091
  codename=$(. /etc/os-release && echo "$VERSION_CODENAME")
  case "$arch-$codename" in
    amd64-noble)                   asset="sunshine-ubuntu-24.04-amd64.deb" ;;
    arm64-noble)                   asset="sunshine-ubuntu-24.04-arm64.deb" ;;
    amd64-resolute)                asset="sunshine-ubuntu-24.04-amd64.deb" ;;
    arm64-resolute)                asset="sunshine-ubuntu-24.04-arm64.deb" ;;
    amd64-jammy)                   asset="sunshine-ubuntu-22.04-amd64.deb" ;;
    arm64-jammy)                   asset="sunshine-ubuntu-22.04-arm64.deb" ;;
    *) log "no known Sunshine package for $arch/$codename"; exit 1 ;;
  esac

  : "${SUNSHINE_VERSION:?SUNSHINE_VERSION must be set in .env}"
  url="https://github.com/LizardByte/Sunshine/releases/download/v${SUNSHINE_VERSION}/${asset}"

  deb="$DOWNLOADS_DIR/$asset"
  download "$url" "$deb"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$deb"
else
  log "sunshine already installed — skipping install"
fi

install_sunshine_compat_libs

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

mkdir -p "$HOME/.local/bin"
if [ ! -x "$HOME/.local/bin/egame-set-display-mode" ]; then
  cat > "$HOME/.local/bin/egame-set-display-mode" <<'EOF'
#!/usr/bin/env sh
exit 0
EOF
  chmod +x "$HOME/.local/bin/egame-set-display-mode"
fi

write_sunshine_apps() {
  local include_steam=0
  { has_pkg steam || command -v steam >/dev/null 2>&1; } && include_steam=1
  if [ "$include_steam" -eq 1 ]; then
    cat > "$HOME/.config/sunshine/apps.json" <<'EOF'
{
  "env": {
    "PATH": "$(PATH):$(HOME)/.local/bin"
  },
  "apps": [
    {
      "name": "Desktop",
      "image-path": "desktop.png",
      "prep-cmd": [
        {
          "do": "$(HOME)/.local/bin/egame-set-display-mode",
          "undo": ""
        }
      ]
    },
    {
      "name": "Steam",
      "cmd": "steam -bigpicture",
      "detached": [
        "setsid steam -bigpicture >/tmp/egame-steam.log 2>&1"
      ],
      "image-path": "steam.png",
      "prep-cmd": [
        {
          "do": "$(HOME)/.local/bin/egame-set-display-mode",
          "undo": ""
        }
      ]
    }
  ]
}
EOF
  else
    cat > "$HOME/.config/sunshine/apps.json" <<'EOF'
{
  "env": {
    "PATH": "$(PATH):$(HOME)/.local/bin"
  },
  "apps": [
    {
      "name": "Desktop",
      "image-path": "desktop.png",
      "prep-cmd": [
        {
          "do": "$(HOME)/.local/bin/egame-set-display-mode",
          "undo": ""
        }
      ]
    }
  ]
}
EOF
  fi
}

log "### 60_sunshine: writing controlled Sunshine app list"
write_sunshine_apps

XDG_RUNTIME_DIR="/run/user/$(id -u)"
export XDG_RUNTIME_DIR
SUN_DISPLAY="${SUNSHINE_DISPLAY:-:0}"
SUN_XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

sudo loginctl enable-linger "$USER"
systemctl --user enable sunshine 2>/dev/null || true
systemctl --user add-wants default.target sunshine.service 2>/dev/null || true
systemctl --user stop sunshine 2>/dev/null || true
pkill -u "$USER" -x sunshine 2>/dev/null || true

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
  if [ -x "$HOME/.local/bin/egame-set-display-mode" ]; then
    "$HOME/.local/bin/egame-set-display-mode" || true
  fi
  systemctl --user import-environment DISPLAY XAUTHORITY XDG_RUNTIME_DIR 2>/dev/null || true
  systemctl --user reset-failed sunshine 2>/dev/null || true
  if ! systemctl --user start sunshine 2>/dev/null; then
    setsid nohup sunshine "$SUN_CONF" >>"$LOGS_DIR/sunshine.log" 2>&1 < /dev/null &
  fi
}

if systemctl --user is-active sunshine >/dev/null 2>&1; then
  log "### 60_sunshine: restarting sunshine to reload config"
  export DISPLAY="$SUN_DISPLAY"
  export XAUTHORITY="$SUN_XAUTHORITY"
  if [ -x "$HOME/.local/bin/egame-set-display-mode" ]; then
    "$HOME/.local/bin/egame-set-display-mode" || true
  fi
  systemctl --user reset-failed sunshine 2>/dev/null || true
  systemctl --user restart sunshine 2>/dev/null || true
elif [ -d "$XDG_RUNTIME_DIR" ] && { sunshine_display_ready || sunshine_kms_ready; }; then
  log "### 60_sunshine: starting sunshine on display $SUN_DISPLAY"
  start_sunshine_with_display
else
  log "### 60_sunshine: no usable user display yet — sunshine will start at next autologin"
fi

log "### 60_sunshine: done"
