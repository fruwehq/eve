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

if [ ! -d /usr/share/xsessions ] || [ -z "$(ls -A /usr/share/xsessions/ 2>/dev/null)" ]; then
  log "### 46_vnc: no desktop session found, installing ubuntu-desktop-minimal"
  DEBIAN_FRONTEND=noninteractive apt-get install -y ubuntu-desktop-minimal
fi

mkdir -p ~/.vnc

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
export XDG_CURRENT_DESKTOP=ubuntu:GNOME
export GDK_BACKEND=x11
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
eval $(dbus-launch --sh-syntax)
gnome-session &
exec sleep infinity
XEOF
  chmod +x ~/.vnc/xstartup
fi

if ss -tlnp 2>/dev/null | grep -q ':5900 '; then
  log "### 46_vnc: VNC server already running on port 5900"
else
  log "### 46_vnc: starting VNC server on :0 (port 5900)"
  tigervncserver :0 -geometry 1920x1080 -depth 24 -SecurityTypes VncAuth -AlwaysShared 2>/dev/null || true
  sleep 2
fi

if ss -tlnp 2>/dev/null | grep -q ':5900 '; then
  log "### 46_vnc: VNC server running on port 5900"
else
  log "### 46_vnc: WARNING — VNC server may not be running. Check ~/.vnc/*.log"
fi

log "### 46_vnc: done"
