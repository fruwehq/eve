#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg rustdesk

if ! is_desktop; then
  log "### 50_rustdesk: headless OS — skipping"
  exit 0
fi

log "### 50_rustdesk: installing RustDesk"

if ! command -v rustdesk >/dev/null 2>&1; then
  arch=$(dpkg --print-architecture)
  case "$arch" in
    amd64) asset="rustdesk-1.3.9-x86_64.deb" ;;
    arm64) asset="rustdesk-1.3.9-aarch64.deb" ;;
    *) log "unsupported arch for RustDesk: $arch"; exit 1 ;;
  esac

  deb="$DOWNLOADS_DIR/$asset"
  download "https://github.com/rustdesk/rustdesk/releases/download/1.3.9/$asset" "$deb"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$deb"
else
  log "rustdesk already installed — skipping install"
fi

mkdir -p "$HOME/.config/rustdesk"
sudo mkdir -p /root/.config/rustdesk

# Stop service before writing config — daemon overwrites files on startup/exit
sudo systemctl stop rustdesk 2>/dev/null || true
sudo killall -9 rustdesk 2>/dev/null || true
sleep 1

# Write server/key directly to config files (works without DISPLAY)
if [ -n "${RUSTDESK_SERVER:-}" ]; then
  log "### 50_rustdesk: configuring server=${RUSTDESK_SERVER}"
  for cfg in "$HOME/.config/rustdesk/RustDesk2.toml" /root/.config/rustdesk/RustDesk2.toml; do
    sudo touch "$cfg"
    if grep -q '^custom-rendezvous-server' "$cfg" 2>/dev/null; then
      sudo sed -i "s|^custom-rendezvous-server.*|custom-rendezvous-server = '${RUSTDESK_SERVER}'|" "$cfg"
    else
      echo "custom-rendezvous-server = '${RUSTDESK_SERVER}'" | sudo tee -a "$cfg" >/dev/null
    fi
    if grep -q '^rendezvous_server' "$cfg" 2>/dev/null; then
      sudo sed -i "s|^rendezvous_server.*|rendezvous_server = '${RUSTDESK_SERVER}:21116'|" "$cfg"
    else
      echo "rendezvous_server = '${RUSTDESK_SERVER}:21116'" | sudo tee -a "$cfg" >/dev/null
    fi
  done
fi

if [ -n "${RUSTDESK_KEY:-}" ]; then
  log "### 50_rustdesk: configuring key"
  for cfg in "$HOME/.config/rustdesk/RustDesk2.toml" /root/.config/rustdesk/RustDesk2.toml; do
    sudo touch "$cfg"
    if grep -q '^key ' "$cfg" 2>/dev/null; then
      sudo sed -i "s|^key .*|key = '${RUSTDESK_KEY}'|" "$cfg"
    else
      echo "key = '${RUSTDESK_KEY}'" | sudo tee -a "$cfg" >/dev/null
    fi
  done
fi

# Start service — it will read our config files on launch
sudo systemctl enable --now rustdesk 2>/dev/null || true

# Wait for daemon to be ready
for i in $(seq 1 10); do
  if rustdesk --get-id >/dev/null 2>&1; then
    break
  fi
  log "### 50_rustdesk: waiting for daemon ($i/10)..."
  sleep 2
done

# Set password via CLI (needs daemon + DISPLAY)
if [ -n "${RUSTDESK_PASSWORD:-}" ]; then
  log "### 50_rustdesk: setting permanent password"
  DISPLAY_NUM=$(find /tmp/.X11-unix/ -maxdepth 1 -name 'X*' -printf '%f' 2>/dev/null | head -1 | sed 's/X//' || true)
  DISPLAY=":${DISPLAY_NUM:-1}" sudo -E rustdesk --password "$RUSTDESK_PASSWORD" 2>&1 || true
fi

log "### 50_rustdesk: done"
