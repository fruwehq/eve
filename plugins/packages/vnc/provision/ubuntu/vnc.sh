#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg vnc

log "### vnc: installing TigerVNC server and tools"

repair_human_desktop_dirs

if command -v tigervncserver >/dev/null 2>&1; then
  log "tigervncserver already installed — skipping install"
else
  apt_install tigervnc-standalone-server tigervnc-common tigervnc-tools dbus-x11
fi

if ! dpkg -s tigervnc-tools >/dev/null 2>&1; then
  apt_install tigervnc-tools
fi

if ! dpkg -s dbus-x11 >/dev/null 2>&1; then
  apt_install dbus-x11
fi

if ! dpkg -s autocutsel >/dev/null 2>&1; then
  apt_install autocutsel
fi

if ! command -v startxfce4 >/dev/null 2>&1; then
  log "### vnc: installing XFCE desktop (GNOME Shell does not work under VNC)"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y xfce4 xfce4-terminal
elif ! command -v xfce4-terminal >/dev/null 2>&1; then
  log "### vnc: installing XFCE terminal emulator"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y xfce4-terminal
fi
ensure_xfce_terminal

VNC_VERSION=$(dpkg-query -W -f '${Version}' tigervnc-standalone-server 2>/dev/null | grep -oP '^\d+\.\d+' || echo "0.0")
if dpkg --compare-versions "$VNC_VERSION" ge "1.15"; then
  VNC_HOME="$HUMAN_HOME/.config/tigervnc"
  sudo rm -rf "$HUMAN_HOME/.vnc"
else
  VNC_HOME="$HUMAN_HOME/.vnc"
fi
human_install_dir "$VNC_HOME"

# Suppress the colord polkit prompt that appears on every XFCE/VNC session.
# Ubuntu 26.04 (polkit 124+) silently ignores the legacy .pkla format — use the
# JavaScript rule format under /etc/polkit-1/rules.d/ instead.
POLKIT_RULE=/etc/polkit-1/rules.d/45-allow-colord.rules
if ! sudo test -f "$POLKIT_RULE"; then
  log "### vnc: adding polkit rule for colord (rules.d / JS)"
  sudo tee "$POLKIT_RULE" > /dev/null << 'EOF'
polkit.addRule(function(action, subject) {
    if (action.id.match(/^org\.freedesktop\.color-manager\./)) {
        return polkit.Result.YES;
    }
});
EOF
  sudo systemctl restart polkit 2>/dev/null || true
fi
if [ ! -f "$VNC_HOME/passwd" ]; then
  log "### vnc: setting VNC password"
  printf 'vagrant\nvagrant\nn\n' | sudo -H -u "$HUMAN_USER_NAME" tigervncpasswd 2>&1
fi

XSTARTUP_CONTENT=$(cat <<'XEOF'
#!/bin/sh
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
export XDG_SESSION_TYPE=x11
export XDG_CURRENT_DESKTOP=XFCE
export GDK_BACKEND=x11
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_CACHE_HOME="$HOME/.cache"
[ -f "$XDG_CONFIG_HOME/user-dirs.dirs" ] && . "$XDG_CONFIG_HOME/user-dirs.dirs"
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
eval $(dbus-launch --sh-syntax)
if command -v vncconfig >/dev/null 2>&1; then
  vncconfig -nowin &
fi
if command -v autocutsel >/dev/null 2>&1; then
  autocutsel -fork -selection PRIMARY
  autocutsel -fork -selection CLIPBOARD
fi
startxfce4 &
sleep 5
if ! pgrep -u "$(id -u)" -x xfdesktop >/dev/null 2>&1; then
  xfdesktop &
fi
if ! pgrep -u "$(id -u)" -x xfce4-panel >/dev/null 2>&1; then
  xfce4-panel &
fi
exec sleep infinity
XEOF
)

XSTARTUP_CHANGED=0
if [ ! -f "$VNC_HOME/xstartup" ] || [ "$XSTARTUP_CONTENT" != "$(cat "$VNC_HOME/xstartup")" ]; then
  log "### vnc: writing xstartup script"
  printf '%s\n' "$XSTARTUP_CONTENT" | human_write_file "$VNC_HOME/xstartup" 0755
  XSTARTUP_CHANGED=1
fi

# VNC should use the same configured display size as the VM unless a VNC-only
# override is provided by the caller.
VNC_GEOMETRY="${VNC_GEOMETRY:-${EPHEMERAL_DISPLAY_RESOLUTION:-1920x1080}}"

UNIT_PATH=/etc/systemd/system/vncserver.service
UNIT_CONTENT=$(cat <<EOF
[Unit]
Description=TigerVNC server on display :1
After=network.target

[Service]
Type=forking
User=$HUMAN_USER_NAME
Environment=HOME=$HUMAN_HOME
ExecStartPre=/bin/sh -c '/usr/bin/vncserver -kill :1 2>/dev/null || true'
ExecStart=/usr/bin/vncserver :1 -geometry $VNC_GEOMETRY -depth 24 -SecurityTypes VncAuth -AlwaysShared
ExecStop=/usr/bin/vncserver -kill :1
Restart=on-success
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
)

UNIT_CHANGED=0
if ! sudo test -f "$UNIT_PATH" || ! echo "$UNIT_CONTENT" | sudo cmp -s - "$UNIT_PATH"; then
  log "### vnc: writing systemd system unit for VNC"
  echo "$UNIT_CONTENT" | sudo tee "$UNIT_PATH" >/dev/null
  sudo systemctl daemon-reload
  UNIT_CHANGED=1
fi

if sudo systemctl is-enabled vncserver.service >/dev/null 2>&1; then
  log "### vnc: VNC system unit already enabled"
else
  log "### vnc: enabling VNC system unit"
  sudo systemctl enable vncserver.service
fi

vnc_listening() {
  ss -tlnp 2>/dev/null | grep -q ':5901 '
}

clear_vnc_display_1() {
  sudo -H -u "$HUMAN_USER_NAME" /usr/bin/vncserver -kill :1 >/dev/null 2>&1 || true
  sudo pkill -u "$HUMAN_USER_NAME" -f 'Xtigervnc :1|vncserver :1' >/dev/null 2>&1 || true
  sudo rm -f /tmp/.X1-lock /tmp/.X11-unix/X1
}

start_vnc_service() {
  local action="$1"
  local attempt
  for attempt in 1 2 3; do
    sudo systemctl reset-failed vncserver.service >/dev/null 2>&1 || true
    sudo systemctl "$action" vncserver.service >/dev/null 2>&1 || true
    sleep 3
    if sudo systemctl is-active vncserver.service >/dev/null 2>&1 && vnc_listening; then
      return 0
    fi
    log "### vnc: display :1 not ready after ${action} attempt $attempt/3; resetting"
    clear_vnc_display_1
    action=start
    sleep 2
  done
  return 1
}

if sudo systemctl is-active vncserver.service >/dev/null 2>&1 && ! vnc_listening; then
  log "### vnc: restarting VNC system unit on display :1"
  start_vnc_service restart || true
elif [ "$UNIT_CHANGED" = "1" ] && sudo systemctl is-active vncserver.service >/dev/null 2>&1; then
  log "### vnc: restarting VNC system unit after unit change"
  start_vnc_service restart || true
elif [ "$XSTARTUP_CHANGED" = "1" ] && sudo systemctl is-active vncserver.service >/dev/null 2>&1; then
  log "### vnc: restarting VNC system unit after xstartup change"
  start_vnc_service restart || true
elif sudo systemctl is-active vncserver.service >/dev/null 2>&1 && vnc_listening; then
  log "### vnc: VNC server already running"
else
  log "### vnc: starting VNC system unit"
  start_vnc_service start || true
fi

if sudo systemctl is-active vncserver.service >/dev/null 2>&1; then
  log "### vnc: VNC server running (systemd unit)"
elif vnc_listening; then
  log "### vnc: VNC server running on port 5901"
else
  log "### vnc: WARNING — VNC server may not be running. Check: sudo systemctl status vncserver.service"
fi

log "### vnc: done"
