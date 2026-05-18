#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg rdp

repair_human_desktop_dirs

configure_gnome_remote_desktop() {
  log "### rdp: installing GNOME Remote Desktop system RDP"

  apt_install \
    dbus-x11 \
    gdm3 \
    gnome-remote-desktop \
    gnome-session \
    gnome-shell \
    gnome-terminal \
    openssl

  sudo systemctl set-default graphical.target
  printf '/usr/sbin/gdm3\n' | sudo tee /etc/X11/default-display-manager >/dev/null
  sudo systemctl disable --now lightdm.service xrdp.service >/dev/null 2>&1 || true
  sudo systemctl enable --now gdm.service >/dev/null 2>&1 ||
    sudo systemctl enable --now gdm3.service >/dev/null 2>&1 || true

  local gate_user="${RDP_GATE_USER:-$HUMAN_USER_NAME}"
  local gate_password="${RDP_GATE_PASSWORD:-${VM_USER_PASSWORD:-}}"
  if [ -z "$gate_password" ]; then
    log "### rdp: VM_USER_PASSWORD or RDP_GATE_PASSWORD is required for GNOME Remote Desktop credentials"
    exit 2
  fi

  local grd_user="gnome-remote-desktop"
  local grd_home
  grd_home="$(getent passwd "$grd_user" | cut -d: -f6)"
  if [ -z "$grd_home" ]; then
    log "### rdp: gnome-remote-desktop user not found"
    exit 2
  fi

  local grd_dir="$grd_home/.local/share/gnome-remote-desktop"
  sudo install -d -o "$grd_user" -g "$grd_user" -m 0700 "$grd_dir"
  if [ ! -f "$grd_dir/tls.key" ] || [ ! -f "$grd_dir/tls.crt" ]; then
    log "### rdp: creating GNOME Remote Desktop TLS certificate"
    sudo openssl req -x509 -nodes -newkey rsa:4096 \
      -keyout "$grd_dir/tls.key" \
      -out "$grd_dir/tls.crt" \
      -days 3650 \
      -subj "/CN=$(hostname)" >/dev/null 2>&1
    sudo chown "$grd_user:$grd_user" "$grd_dir/tls.key" "$grd_dir/tls.crt"
    sudo chmod 0600 "$grd_dir/tls.key"
    sudo chmod 0644 "$grd_dir/tls.crt"
  fi

  sudo systemctl daemon-reload
  sudo grdctl --system rdp set-auth-methods credentials
  sudo grdctl --system rdp set-tls-key "$grd_dir/tls.key"
  sudo grdctl --system rdp set-tls-cert "$grd_dir/tls.crt"
  sudo grdctl --system rdp set-credentials "$gate_user" "$gate_password"
  sudo grdctl --system rdp disable-view-only
  sudo grdctl --system rdp enable

  sudo systemctl enable --now gnome-remote-desktop.service
  sudo systemctl restart gnome-remote-desktop.service
}

configure_xrdp_xfce() {
  log "### rdp: installing xrdp"

missing_packages=()
for pkg in xrdp xorgxrdp dbus-x11 xfce4 xfce4-terminal; do
  if ! dpkg -s "$pkg" >/dev/null 2>&1; then
    missing_packages+=("$pkg")
  fi
done

if [ "${#missing_packages[@]}" -gt 0 ]; then
  apt_install "${missing_packages[@]}"
else
  log "xrdp desktop packages already installed"
fi
ensure_xfce_terminal

cat <<'EOF' | human_write_file "$HUMAN_HOME/.xsession" 0644
#!/usr/bin/env sh
unset DBUS_SESSION_BUS_ADDRESS
unset SESSION_MANAGER
export XDG_SESSION_TYPE=x11
export XDG_CURRENT_DESKTOP=XFCE
exec dbus-run-session -- startxfce4
EOF

sudo adduser xrdp ssl-cert >/dev/null 2>&1 || true
sudo systemctl enable --now xrdp
sudo systemctl restart xrdp
}

if has_pkg gnome-desktop; then
  configure_gnome_remote_desktop
else
  configure_xrdp_xfce
fi

log "### rdp: done"
