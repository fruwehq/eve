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

if ! systemctl list-unit-files display-manager.service >/dev/null 2>&1; then
  log "### 50_rustdesk: installing LightDM display manager"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y lightdm
fi

log "### 50_rustdesk: configuring LightDM autologin"
sudo mkdir -p /etc/lightdm/lightdm.conf.d
sudo tee /etc/lightdm/lightdm.conf.d/50-ephemeral-autologin.conf >/dev/null <<EOF
[Seat:*]
autologin-user=$USER
autologin-user-timeout=0
user-session=xfce
EOF

if [ "${PROVIDER:-}" = "raspberry-pi" ]; then
  hdmi_connector="${RASPBERRY_PI_HDMI_CONNECTOR:-HDMI-A-1}"
  hdmi_mode="${RASPBERRY_PI_HDMI_MODE:-1024x768@60D}"
  xrandr_output="${hdmi_connector/HDMI-A/HDMI}"
  xrandr_mode="${hdmi_mode%@*}"
  xrandr_mode="${xrandr_mode%D}"
  hdmi_token="video=${hdmi_connector}:${hdmi_mode}"
  if [ -w /boot/firmware/cmdline.txt ] || sudo test -w /boot/firmware/cmdline.txt; then
    if ! grep -qwF "$hdmi_token" /boot/firmware/cmdline.txt; then
      log "### 50_rustdesk: forcing Raspberry Pi headless HDMI mode $hdmi_token"
      sudo cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.egame.bak
      sudo sed -i -E "s#(^| )video=${hdmi_connector}:[^ ]+##g; s#\$# ${hdmi_token}#" /boot/firmware/cmdline.txt
      log "### 50_rustdesk: reboot required for $hdmi_token to take effect"
    fi
  else
    log "### 50_rustdesk: warn: /boot/firmware/cmdline.txt not writable; cannot force headless HDMI"
  fi

  sudo mkdir -p /etc/X11/xorg.conf.d
  sudo tee /etc/X11/xorg.conf.d/10-raspi-kms.conf >/dev/null <<EOF
Section "Device"
    Identifier "Raspberry Pi KMS Display"
    Driver "modesetting"
    Option "kmsdev" "/dev/dri/card1"
EndSection
EOF

  mkdir -p "$HOME/.config/autostart"
  cat > "$HOME/.config/autostart/egame-display-mode.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Set display mode
Exec=sh -c 'xrandr --output "$xrandr_output" --mode "$xrandr_mode" 2>/dev/null || true'
Hidden=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF
fi

# LightDM's pam_succeed_if rule for the autologin path keys off the `autologin`
# group on Debian/Ubuntu; ensure the user is in it. Cloud-init Ubuntu users have
# `*` in /etc/shadow which blocks pam_unix during the lock-screen unlock — having
# the user in `nopasswdlogin` bypasses the password challenge entirely.
sudo groupadd --system autologin 2>/dev/null || true
sudo groupadd --system nopasswdlogin 2>/dev/null || true
sudo usermod -aG autologin "$USER"
sudo usermod -aG nopasswdlogin "$USER"

# Without this, xfce4-screensaver/light-locker locks the auto-logged-in session
# after a few minutes and prompts for the user's (often-unset) Unix password,
# which is the prompt RustDesk shows after auth.
sudo DEBIAN_FRONTEND=noninteractive apt-get remove -y --purge xfce4-screensaver light-locker 2>/dev/null || true
sudo systemctl disable --now xfce4-screensaver.service 2>/dev/null || true

# Belt-and-suspenders: pin the xfconf settings so even if a screensaver gets
# pulled back in by another package, it stays disabled.
mkdir -p "$HOME/.config/xfce4/xfconf/xfce-perchannel-xml"
cat > "$HOME/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-screensaver.xml" <<'XEOF'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-screensaver" version="1.0">
  <property name="lock" type="empty">
    <property name="enabled" type="bool" value="false"/>
  </property>
  <property name="saver" type="empty">
    <property name="enabled" type="bool" value="false"/>
  </property>
</channel>
XEOF

mkdir -p "$HOME/.config/rustdesk"
sudo mkdir -p /root/.config/rustdesk

# Clear leftover immutable flag from a prior buggy provisioning run
sudo chattr -i "$HOME/.config/rustdesk/RustDesk2.toml" 2>/dev/null || true
sudo chattr -i /root/.config/rustdesk/RustDesk2.toml 2>/dev/null || true

# Stop the daemon so it doesn't rewrite the file while we edit it
sudo systemctl stop rustdesk 2>/dev/null || true
sudo killall -9 rustdesk 2>/dev/null || true
sudo systemctl disable --now rustdesk-vnc-server.service >/dev/null 2>&1 || true
rm -f "$HOME/.config/systemd/user/rustdesk-vnc-server.service"
XDG_RUNTIME_DIR="/run/user/$(id -u)" systemctl --user disable --now rustdesk-vnc-server.service >/dev/null 2>&1 || true
sleep 1

# Write the file from scratch so our keys land inside the [options] section.
# Top-level keys (rendezvous_server, nat_type, ...) are runtime state the daemon
# rewrites; [options] is user preferences and is preserved across daemon writes.
write_rustdesk_config() {
  local cfg="$1"
  sudo mkdir -p "$(dirname "$cfg")"
  {
    [ -n "${RUSTDESK_SERVER:-}" ] && echo "rendezvous_server = '${RUSTDESK_SERVER}:21116'"
    echo
    echo "[options]"
    [ -n "${RUSTDESK_SERVER:-}" ] && {
      echo "custom-rendezvous-server = '${RUSTDESK_SERVER}'"
      echo "relay-server = '${RUSTDESK_SERVER}'"
    }
    [ -n "${RUSTDESK_KEY:-}" ] && echo "key = '${RUSTDESK_KEY}'"
    if [ -n "${RUSTDESK_PASSWORD:-}" ]; then
      # Default verification-method is OTP — flip to permanent so RUSTDESK_PASSWORD
      # is what the client authenticates with. approve-mode=password auto-accepts
      # a correct password without local-user confirmation.
      echo "verification-method = 'use-permanent-password'"
      echo "approve-mode = 'password'"
    fi
  } | sudo tee "$cfg" >/dev/null
}

for cfg in "$HOME/.config/rustdesk/RustDesk2.toml" /root/.config/rustdesk/RustDesk2.toml; do
  log "### 50_rustdesk: writing $cfg"
  write_rustdesk_config "$cfg"
done

# Start daemon — reads our config on launch
sudo systemctl set-default graphical.target >/dev/null 2>&1 || true
sudo systemctl enable --now display-manager.service >/dev/null 2>&1 || true
sudo systemctl enable --now lightdm.service >/dev/null 2>&1 || true
sudo systemctl restart lightdm.service >/dev/null 2>&1 || true
sudo systemctl enable --now rustdesk 2>/dev/null || true

# Wait for the root service to come up.
for i in $(seq 1 15); do
  if rustdesk --get-id >/dev/null 2>&1; then
    break
  fi
  log "### 50_rustdesk: waiting for daemon ($i/15)..."
  sleep 2
done

rd_user="$USER"
rd_uid=$(id -u "$rd_user")
rd_server_ready=0

for i in $(seq 1 15); do
  if ps -eo user,cmd 2>/dev/null | awk -v user="$rd_user" '$1==user && /[r]ustdesk/ && /--server/ {found=1} END {exit !found}'; then
    rd_server_ready=1
    break
  fi
  log "### 50_rustdesk: waiting for user server ($i/15)..."
  sleep 1
done

# Set permanent password — must run after the user-side `rustdesk --server`
# owns its IPC socket.
if [ -n "${RUSTDESK_PASSWORD:-}" ]; then
  log "### 50_rustdesk: setting permanent password"
  if [ "$rd_server_ready" -ne 1 ]; then
    log "### 50_rustdesk: warn: user server was not detected; attempting --password for $rd_user anyway"
  fi
  if sudo rustdesk --password "$RUSTDESK_PASSWORD"; then
    log "### 50_rustdesk: permanent password set via admin service"
  elif env HOME="$HOME" XDG_RUNTIME_DIR="/run/user/$rd_uid" rustdesk --password "$RUSTDESK_PASSWORD"; then
    log "### 50_rustdesk: permanent password set via user server"
  else
    log "### 50_rustdesk: warn: --password failed (server-user=$rd_user); client will be prompted to set one"
  fi
fi

log "### 50_rustdesk: done"
