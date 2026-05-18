#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg xfce-desktop-headless

log "### xfce-desktop-headless: installing XFCE headless session"

apt_install \
  dbus-x11 \
  openssl \
  xfce4 \
  xfce4-terminal \
  xterm

configure_xfce_xsession
disable_xfce_locks
sudo systemctl disable --now lightdm.service gdm.service gdm3.service sddm.service >/dev/null 2>&1 || true
sudo systemctl set-default multi-user.target

log "### xfce-desktop-headless: done"
