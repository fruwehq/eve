#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg thinlinc

log "### thinlinc: installing ThinLinc server"

write_xstartup() {
  human_install_dir "$HUMAN_HOME/.thinlinc"
  if has_pkg gnome-desktop; then
    cat <<'EOF' | human_write_file "$HUMAN_HOME/.thinlinc/xstartup" 0755
#!/bin/bash
unset SESSION_MANAGER
unset WAYLAND_DISPLAY
export XDG_SESSION_TYPE=x11
export XDG_CURRENT_DESKTOP=GNOME
export XDG_SESSION_DESKTOP=gnome
export DESKTOP_SESSION=gnome
export GDK_BACKEND=x11
export QT_QPA_PLATFORM=xcb
export CLUTTER_BACKEND=x11
export MUTTER_DEBUG_FORCE_KMS_MODE=simple
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path="$XDG_RUNTIME_DIR/bus"
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_CACHE_HOME="$HOME/.cache"
[ -f "$XDG_CONFIG_HOME/user-dirs.dirs" ] && . "$XDG_CONFIG_HOME/user-dirs.dirs"

if [ -n "${TLPREFIX:-}" ] && [ -f "${TLPREFIX}/libexec/tl-run-xstartup.d" ]; then
  # shellcheck disable=SC1091
  source "${TLPREFIX}/libexec/tl-run-xstartup.d"
fi

gnome-session --session=gnome
status=$?

if [ -n "${TLPREFIX:-}" ] && [ -f "${TLPREFIX}/libexec/tl-run-xlogout.d" ]; then
  # shellcheck disable=SC1091
  source "${TLPREFIX}/libexec/tl-run-xlogout.d"
fi

exit "$status"
EOF
  else
    cat <<'EOF' | human_write_file "$HUMAN_HOME/.thinlinc/xstartup" 0755
#!/bin/bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
unset WAYLAND_DISPLAY
export XDG_SESSION_TYPE=x11
export XDG_CURRENT_DESKTOP=XFCE
export XDG_SESSION_DESKTOP=xfce
export GDK_BACKEND=x11
export QT_QPA_PLATFORM=xcb
export CLUTTER_BACKEND=x11
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_CACHE_HOME="$HOME/.cache"
[ -f "$XDG_CONFIG_HOME/user-dirs.dirs" ] && . "$XDG_CONFIG_HOME/user-dirs.dirs"

if [ -n "${TLPREFIX:-}" ] && [ -f "${TLPREFIX}/libexec/tl-run-xstartup.d" ]; then
  # shellcheck disable=SC1091
  source "${TLPREFIX}/libexec/tl-run-xstartup.d"
fi

dbus-run-session -- startxfce4
status=$?

if [ -n "${TLPREFIX:-}" ] && [ -f "${TLPREFIX}/libexec/tl-run-xlogout.d" ]; then
  # shellcheck disable=SC1091
  source "${TLPREFIX}/libexec/tl-run-xlogout.d"
fi

exit "$status"
EOF
  fi
}

configure_gnome_profile() {
  has_pkg gnome-desktop || return 0

  log "### thinlinc: configuring GNOME as the default ThinLinc profile"
  log "### thinlinc: disabling local GDM session for ThinLinc GNOME"
  sudo systemctl disable --now gdm3.service gdm.service 2>/dev/null || true
  sudo install -d -m 0755 /usr/share/xsessions
  sudo tee /usr/share/xsessions/gnome.desktop >/dev/null <<'EOF'
[Desktop Entry]
Name=GNOME
Comment=GNOME desktop session
Exec=env XDG_SESSION_TYPE=x11 XDG_CURRENT_DESKTOP=GNOME XDG_SESSION_DESKTOP=gnome DESKTOP_SESSION=gnome GDK_BACKEND=x11 QT_QPA_PLATFORM=xcb CLUTTER_BACKEND=x11 gnome-session --session=gnome
TryExec=gnome-session
Type=Application
DesktopNames=GNOME
EOF

  if [ -x /opt/thinlinc/bin/tl-config ]; then
    sudo /opt/thinlinc/bin/tl-config /profiles/default=gnome
    sudo /opt/thinlinc/bin/tl-config /profiles/show_intro=false
  elif [ -f /opt/thinlinc/etc/conf.d/profiles.hconf ]; then
    sudo sed -i \
      -e 's/^default=.*/default=gnome/' \
      -e 's/^show_intro=.*/show_intro=false/' \
      /opt/thinlinc/etc/conf.d/profiles.hconf
  fi
}

configure_agent_hostname() {
  if [ -z "${THINLINC_AGENT_HOSTNAME:-}" ]; then
    log "### thinlinc: THINLINC_AGENT_HOSTNAME not set; leaving vsmagent hostname unchanged"
    return 0
  fi

  if [ ! -x /opt/thinlinc/bin/tl-config ]; then
    log "### thinlinc: tl-config not found; cannot set vsmagent agent_hostname yet"
    return 0
  fi

  log "### thinlinc: setting /vsmagent/agent_hostname=$THINLINC_AGENT_HOSTNAME"
  sudo /opt/thinlinc/bin/tl-config "/vsmagent/agent_hostname=$THINLINC_AGENT_HOSTNAME"
}

if systemctl is-active --quiet vsmserver.service 2>/dev/null &&
  systemctl is-active --quiet vsmagent.service 2>/dev/null &&
  systemctl is-active --quiet tlwebaccess.service 2>/dev/null; then
  log "ThinLinc services already running — ensuring user session launcher"
  repair_human_desktop_dirs
  if has_pkg gnome-desktop; then
    apt_install dbus-x11 gnome-session gnome-shell gnome-terminal
  else
    apt_install dbus-x11 xfce4 xfce4-terminal
    ensure_xfce_terminal
  fi
  write_xstartup
  configure_gnome_profile
  configure_agent_hostname
  sudo systemctl restart vsmagent.service tlwebaccess.service
  log "### thinlinc: done"
  exit 0
fi

case "${THINLINC_ACCEPT_EULA:-}" in
  yes|true) ;;
  *)
    log "### thinlinc: THINLINC_ACCEPT_EULA=yes is required before installing ThinLinc"
    log "### thinlinc: get the server bundle from https://www.cendio.com/thinlinc/download/"
    exit 2
    ;;
esac

if [ -z "${THINLINC_SERVER_BUNDLE_URL:-}" ] && [ -z "${THINLINC_SERVER_BUNDLE_PATH:-}" ]; then
  log "### thinlinc: THINLINC_SERVER_BUNDLE_PATH or THINLINC_SERVER_BUNDLE_URL is required"
  log "### thinlinc: Cendio distributes the server bundle through their download flow, so this repo does not hard-code a hidden URL"
  exit 2
fi

repair_human_desktop_dirs
if has_pkg gnome-desktop; then
  apt_install ca-certificates curl unzip dbus-x11 gnome-session gnome-shell gnome-terminal
else
  apt_install ca-certificates curl unzip dbus-x11 xfce4 xfce4-terminal
  ensure_xfce_terminal
fi

workdir=/tmp/egame-thinlinc
bundle="$workdir/thinlinc-server.zip"
sudo rm -rf "$workdir"
sudo mkdir -p "$workdir"
sudo chown "$USER:$USER" "$workdir"

if [ -n "${THINLINC_SERVER_BUNDLE_PATH:-}" ]; then
  if [ ! -e "$THINLINC_SERVER_BUNDLE_PATH" ]; then
    log "### thinlinc: THINLINC_SERVER_BUNDLE_PATH not found: $THINLINC_SERVER_BUNDLE_PATH"
    exit 2
  fi
  if [ -d "$THINLINC_SERVER_BUNDLE_PATH" ]; then
    log "### thinlinc: using uploaded server bundle directory $THINLINC_SERVER_BUNDLE_PATH"
    cp -a "$THINLINC_SERVER_BUNDLE_PATH" "$workdir/server"
  else
    log "### thinlinc: using uploaded server bundle archive $THINLINC_SERVER_BUNDLE_PATH"
    cp "$THINLINC_SERVER_BUNDLE_PATH" "$bundle"
    unzip -q "$bundle" -d "$workdir"
  fi
else
  log "### thinlinc: downloading server bundle"
  curl -fL --retry 3 --retry-delay 3 -o "$bundle" "$THINLINC_SERVER_BUNDLE_URL"
  unzip -q "$bundle" -d "$workdir"
fi

installer=$(find "$workdir" -maxdepth 2 -type f -name install-server | head -n 1)
if [ -z "$installer" ]; then
  log "### thinlinc: install-server not found in downloaded bundle"
  exit 2
fi

server_root=$(dirname "$installer")
log "### thinlinc: installing package files from $server_root"
(
  cd "$server_root"
  if [ -d packages ]; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ./packages/*.deb
  else
    log "### thinlinc: packages directory not found in server bundle"
    exit 2
  fi
)

if [ ! -x /opt/thinlinc/sbin/tl-setup ]; then
  log "### thinlinc: tl-setup was not installed"
  exit 2
fi

answer_template="$workdir/tl-setup.answers"
log "### thinlinc: writing tl-setup answer file"
sudo tee "$answer_template" >/dev/null <<'EOF'
missing-answer=abort
accept-eula=yes
server-type=master
install-required-libs=yes
install-sshd=no
install-nfs=no
install-gtk=yes
install-python-ldap=no
agent-hostname-choice=ip
email-address=root@localhost
tlwebadm-password=
setup-thinlocal=no
setup-nearest=no
setup-firewall-ssh=no
setup-firewall-tlwebaccess=no
setup-firewall-tlwebadm=no
setup-firewall-tlmaster=no
setup-firewall-tlagent=no
setup-apparmor=no
setup-selinux=no
EOF

log "### thinlinc: running tl-setup non-interactively"
DISPLAY= sudo /opt/thinlinc/sbin/tl-setup -a "$answer_template"

configure_agent_hostname

sudo systemctl enable --now vsmserver.service vsmagent.service tlwebaccess.service
sudo systemctl restart vsmserver.service vsmagent.service tlwebaccess.service

write_xstartup
configure_gnome_profile

log "### thinlinc: done"
