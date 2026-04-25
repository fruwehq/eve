#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg vnc

if ! is_desktop; then
  log "### 46_vnc: headless OS — skipping"
  exit 0
fi

log "### 46_vnc: installing TigerVNC server and tools"

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

if ! command -v startxfce4 >/dev/null 2>&1; then
  log "### 46_vnc: installing XFCE desktop (GNOME Shell does not work under VNC)"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y xfce4
fi

mkdir -p ~/.vnc

# Suppress the colord polkit prompt that appears on every XFCE/VNC session.
# Ubuntu 24.04 (polkit 124) silently ignores the legacy .pkla format — use the
# JavaScript rule format under /etc/polkit-1/rules.d/ instead.
POLKIT_RULE=/etc/polkit-1/rules.d/45-allow-colord.rules
if ! sudo test -f "$POLKIT_RULE"; then
  log "### 46_vnc: adding polkit rule for colord (rules.d / JS)"
  sudo tee "$POLKIT_RULE" > /dev/null << 'EOF'
polkit.addRule(function(action, subject) {
    if (action.id.match(/^org\.freedesktop\.color-manager\./)) {
        return polkit.Result.YES;
    }
});
EOF
  sudo systemctl restart polkit 2>/dev/null || true
fi
if [ ! -f ~/.vnc/passwd ]; then
  log "### 46_vnc: setting VNC password"
  printf 'vagrant\nvagrant\nn\n' | tigervncpasswd 2>&1
fi

if [ ! -f ~/.vnc/xstartup ]; then
  log "### 46_vnc: creating xstartup script"
  cat > ~/.vnc/xstartup << 'XEOF'
#!/bin/sh
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
export XDG_SESSION_TYPE=x11
export XDG_CURRENT_DESKTOP=XFCE
export GDK_BACKEND=x11
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
eval $(dbus-launch --sh-syntax)
startxfce4 &
exec sleep infinity
XEOF
  chmod +x ~/.vnc/xstartup
fi

UNIT_PATH=/etc/systemd/system/vncserver.service

if ! sudo test -f "$UNIT_PATH"; then
  log "### 46_vnc: installing systemd system unit for VNC"
  sudo tee "$UNIT_PATH" >/dev/null <<EOF
[Unit]
Description=TigerVNC server on display :0
After=network.target

[Service]
Type=forking
User=$USER
Environment=HOME=$HOME
ExecStartPre=/bin/sh -c '/usr/bin/vncserver -kill :0 2>/dev/null || true'
ExecStart=/usr/bin/vncserver :0 -geometry 1920x1080 -depth 24 -SecurityTypes VncAuth -AlwaysShared
ExecStop=/usr/bin/vncserver -kill :0
Restart=on-success
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
fi

if sudo systemctl is-enabled vncserver.service >/dev/null 2>&1; then
  log "### 46_vnc: VNC system unit already enabled"
else
  log "### 46_vnc: enabling VNC system unit"
  sudo systemctl enable vncserver.service
fi

if sudo systemctl is-active vncserver.service >/dev/null 2>&1; then
  log "### 46_vnc: VNC server already running"
else
  log "### 46_vnc: starting VNC system unit"
  sudo systemctl start vncserver.service || true
  sleep 2
fi

if sudo systemctl is-active vncserver.service >/dev/null 2>&1; then
  log "### 46_vnc: VNC server running (systemd unit)"
elif ss -tlnp 2>/dev/null | grep -q ':5900 '; then
  log "### 46_vnc: VNC server running on port 5900"
else
  log "### 46_vnc: WARNING — VNC server may not be running. Check: sudo systemctl status vncserver.service"
fi

log "### 46_vnc: done"
