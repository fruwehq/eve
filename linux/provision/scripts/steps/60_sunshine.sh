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
if ! grep -q '^origin_web_ui_allowed' "$SUN_CONF"; then
  echo 'origin_web_ui_allowed = wan' >> "$SUN_CONF"
fi

# Set Sunshine web UI credentials (matches Windows step 10's behavior).
if [ -n "${EPHEMERAL_SUNSHINE_PASSWORD:-}" ]; then
  log "### 60_sunshine: setting web UI credentials"
  sunshine "$SUN_CONF" --creds sunshine "$EPHEMERAL_SUNSHINE_PASSWORD" || \
    log "### 60_sunshine: warn: failed to set credentials (will retry on next run)"
else
  log "### 60_sunshine: EPHEMERAL_SUNSHINE_PASSWORD not set — skipping creds"
fi

# Sunshine needs an active X session to capture the screen, so it runs as a
# user-session autostart entry rather than a system service. The XFCE session
# launched by LightDM autologin (configured in 50_rustdesk.sh) fires this.
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/sunshine.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Sunshine
Exec=/usr/bin/sunshine $SUN_CONF
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF

# Try to bring it up immediately if a user session is already running, so
# remote-sunshine-wait can succeed without an extra reboot.
if pgrep -u "$USER" -x sunshine >/dev/null 2>&1; then
  log "### 60_sunshine: sunshine already running"
else
  if [ -n "${DISPLAY:-}" ] || [ -d "/run/user/$(id -u)" ]; then
    log "### 60_sunshine: starting sunshine in current user session"
    setsid nohup sunshine "$SUN_CONF" >>"$LOGS_DIR/sunshine.log" 2>&1 < /dev/null &
  else
    log "### 60_sunshine: no user session yet — sunshine will start at next autologin"
  fi
fi

log "### 60_sunshine: done"
