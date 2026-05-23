#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg gnome-desktop

log "### gnome-desktop: installing GNOME desktop session"

apt_wait
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  dbus-x11 \
  gdm3 \
  gnome-remote-desktop \
  gnome-session \
  gnome-shell \
  gnome-terminal \
  mutter \
  nautilus \
  openssl \
  ubuntu-desktop-minimal \
  ubuntu-session \
  yaru-theme-gtk \
  yaru-theme-icon

log "### gnome-desktop: configuring GDM autologin"
configure_gdm_autologin
start_human_user_manager
disable_gnome_first_run_and_locks

log "### gnome-desktop: done"
