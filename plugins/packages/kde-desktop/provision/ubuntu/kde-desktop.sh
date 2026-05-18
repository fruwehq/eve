#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg kde-desktop

log "### kde-desktop: installing KDE Plasma desktop session"

apt_install \
  dbus-x11 \
  flatpak \
  kde-plasma-desktop \
  krdp \
  openssl \
  sddm

repair_human_desktop_dirs
configure_sddm_autologin
start_human_user_manager

log "### kde-desktop: done"
