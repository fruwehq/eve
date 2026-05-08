#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg gnome-desktop

log "### gnome-desktop: installing GNOME desktop session"

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
  log "### gnome-desktop: preferring GNOME for existing LightDM autologin"
  sudo sed -i 's/^user-session=.*/user-session=gnome/' /etc/lightdm/lightdm.conf.d/50-ephemeral-autologin.conf 2>/dev/null || true
fi

log "### gnome-desktop: done"
