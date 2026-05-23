#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg gnome-desktop-headless

log "### gnome-desktop-headless: installing GNOME headless Wayland session"

apt_install \
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

configure_gdm_autologin
start_human_user_manager
disable_gnome_first_run_and_locks

log "### gnome-desktop-headless: done"
