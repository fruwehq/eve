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
  if [ -n "${RASPBERRY_PI_HDMI_MODE:-}" ]; then
    hdmi_mode="$RASPBERRY_PI_HDMI_MODE"
  elif [ -n "${EPHEMERAL_DISPLAY_RESOLUTION:-}" ]; then
    hdmi_mode="${EPHEMERAL_DISPLAY_RESOLUTION}@60D"
  else
    hdmi_mode="1024x768@60D"
  fi
  xrandr_mode="${hdmi_mode%@*}"
  xrandr_mode="${xrandr_mode%D}"
  if [ -w /boot/firmware/cmdline.txt ] || sudo test -w /boot/firmware/cmdline.txt; then
    if grep -qF "video=${hdmi_connector}:" /boot/firmware/cmdline.txt; then
      log "### 50_rustdesk: removing obsolete Raspberry Pi HDMI-forcing cmdline token"
      sudo cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.egame.bak
      sudo sed -i -E "s#(^| )video=${hdmi_connector}:[^ ]+##g; s#  +# #g; s#^ ##; s# \$##" /boot/firmware/cmdline.txt
    fi
  else
    log "### 50_rustdesk: warn: /boot/firmware/cmdline.txt not writable; cannot clean obsolete HDMI forcing"
  fi

  log "### 50_rustdesk: configuring Raspberry Pi Xorg dummy display $xrandr_mode"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y xserver-xorg-video-dummy
  xrandr_width="${xrandr_mode%x*}"
  xrandr_height="${xrandr_mode#*x}"
  modeline=$(cvt "$xrandr_width" "$xrandr_height" 60 2>/dev/null | awk '/Modeline/ {$1=""; sub(/^ /, ""); print; exit}' || true)
  if [ -z "$modeline" ]; then
    modeline=$(gtf "$xrandr_width" "$xrandr_height" 60 2>/dev/null | awk '/Modeline/ {$1=""; sub(/^ /, ""); print; exit}' || true)
  fi
  if [ -n "$modeline" ]; then
    mode_name=$(printf '%s\n' "$modeline" | awk '{print $1}' | tr -d '"')
    modeline_config="    Modeline $modeline"
  else
    mode_name="$xrandr_mode"
    modeline_config=""
  fi
  sudo mkdir -p /etc/X11/xorg.conf.d
  mkdir -p "$HOME/.local/bin"
  sudo rm -f /etc/X11/xorg.conf.d/10-raspi-kms.conf
  sudo tee /etc/X11/xorg.conf.d/10-ephemeral-dummy-display.conf >/dev/null <<EOF
Section "Device"
    Identifier "Ephemeral Dummy Display"
    Driver "dummy"
    VideoRam 256000
EndSection

Section "Monitor"
    Identifier "Ephemeral Monitor"
    HorizSync 5.0-1000.0
    VertRefresh 5.0-200.0
${modeline_config}
EndSection

Section "Screen"
    Identifier "Ephemeral Screen"
    Device "Ephemeral Dummy Display"
    Monitor "Ephemeral Monitor"
    DefaultDepth 24
    SubSection "Display"
        Depth 24
        Virtual ${xrandr_width} ${xrandr_height}
        Modes "$mode_name" "$xrandr_mode" "1920x1080" "1280x720" "1024x768" "800x600" "640x480"
    EndSubSection
EndSection
EOF

  mkdir -p "$HOME/.config/autostart"
  cat > "$HOME/.local/bin/egame-set-display-mode" <<EOF
#!/usr/bin/env sh
set -eu
export DISPLAY="\${DISPLAY:-:0}"
export XAUTHORITY="\${XAUTHORITY:-$HOME/.Xauthority}"
if ! xrandr --query >/dev/null 2>&1; then
  exit 0
fi
EOF
  if [ -n "$modeline" ]; then
    cat >> "$HOME/.local/bin/egame-set-display-mode" <<EOF
xrandr --newmode $modeline 2>/dev/null || true
xrandr --addmode DUMMY0 "$mode_name" 2>/dev/null || true
EOF
  fi
  cat >> "$HOME/.local/bin/egame-set-display-mode" <<EOF
xrandr --output DUMMY0 --mode "$mode_name" 2>/dev/null || true
EOF
  chmod +x "$HOME/.local/bin/egame-set-display-mode"

  cat > "$HOME/.config/autostart/egame-display-mode.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Set display mode
Exec=$HOME/.local/bin/egame-set-display-mode
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
sudo groupadd --system uinput 2>/dev/null || true
sudo usermod -aG autologin "$USER"
sudo usermod -aG nopasswdlogin "$USER"
sudo usermod -aG input "$USER"
sudo usermod -aG uinput "$USER"

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

  set_rustdesk_password() {
    output=$("$@" 2>&1) || return 1
    printf '%s\n' "$output"
    printf '%s\n' "$output" | grep -q "Done!"
  }

  if set_rustdesk_password sudo rustdesk --password "$RUSTDESK_PASSWORD"; then
    log "### 50_rustdesk: permanent password set via admin service"
  elif set_rustdesk_password env HOME="$HOME" XDG_RUNTIME_DIR="/run/user/$rd_uid" rustdesk --password "$RUSTDESK_PASSWORD"; then
    log "### 50_rustdesk: permanent password set via user server"
  else
    log "### 50_rustdesk: warn: --password failed (server-user=$rd_user); client will be prompted to set one"
  fi
fi

log "### 50_rustdesk: done"
