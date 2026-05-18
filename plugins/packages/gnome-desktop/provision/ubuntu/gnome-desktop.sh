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
sudo systemctl set-default graphical.target
sudo mkdir -p /etc/gdm3
sudo tee /etc/gdm3/custom.conf >/dev/null <<EOF
[daemon]
AutomaticLoginEnable=True
AutomaticLogin=$HUMAN_USER_NAME

[security]

[xdmcp]

[chooser]

[debug]
EOF
sudo rm -f "/var/lib/AccountsService/users/$HUMAN_USER_NAME"
printf '/usr/sbin/gdm3\n' | sudo tee /etc/X11/default-display-manager >/dev/null
sudo systemctl disable --now lightdm.service >/dev/null 2>&1 || true
sudo systemctl enable --now gdm3.service >/dev/null 2>&1 || true

log "### gnome-desktop: done"
