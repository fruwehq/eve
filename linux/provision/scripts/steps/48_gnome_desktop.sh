#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg gnome-desktop

if ! is_desktop; then
  log "### 48_gnome_desktop: headless OS — skipping"
  exit 0
fi

log "### 48_gnome_desktop: installing GNOME desktop session"

apt_install \
  dbus-x11 \
  gdm3 \
  gnome-session \
  gnome-shell \
  gnome-terminal \
  mutter \
  nautilus \
  yaru-theme-gtk \
  yaru-theme-icon

if sudo test -d /etc/lightdm/lightdm.conf.d; then
  log "### 48_gnome_desktop: preferring GNOME for existing LightDM autologin"
  sudo sed -i 's/^user-session=.*/user-session=gnome/' /etc/lightdm/lightdm.conf.d/50-ephemeral-autologin.conf 2>/dev/null || true
fi

log "### 48_gnome_desktop: done"
