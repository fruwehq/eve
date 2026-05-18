#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg xfce-desktop

log "### xfce-desktop: installing XFCE desktop session"

apt_install \
  dbus-x11 \
  lightdm \
  openssl \
  xfce4 \
  xfce4-terminal \
  xterm

configure_xfce_xsession
configure_lightdm_autologin

log "### xfce-desktop: done"
