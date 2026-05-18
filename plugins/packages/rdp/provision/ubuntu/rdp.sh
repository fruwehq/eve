#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg rdp

repair_human_desktop_dirs

rdp_port="${RDP_PORT:-3389}"

grdctl_supports() {
  local pattern="$1"
  grdctl --help 2>&1 | grep -q -- "$pattern" ||
    grdctl rdp --help 2>&1 | grep -q -- "$pattern" ||
    grdctl --system rdp --help 2>&1 | grep -q -- "$pattern" ||
    grdctl --headless rdp --help 2>&1 | grep -q -- "$pattern"
}

configure_gnome_rdp() {
  local headless="$1"
  log "### rdp: configuring GNOME Remote Desktop (${headless})"

  apt_install \
    dbus-x11 \
    gdm3 \
    gnome-keyring \
    gnome-remote-desktop \
    gnome-session \
    gnome-shell \
    gnome-terminal \
    mutter \
    openssl \
    ubuntu-desktop-minimal \
    ubuntu-session

  configure_gdm_autologin
  start_human_user_manager
  disable_gnome_first_run_and_locks

  local gate_user="${RDP_GATE_USER:-rdpuser}"
  local gate_password="${RDP_GATE_PASSWORD:-${VM_USER_PASSWORD:-}}"
  if [ -z "$gate_password" ]; then
    log "### rdp: VM_USER_PASSWORD or RDP_GATE_PASSWORD is required for GNOME Remote Desktop credentials"
    exit 2
  fi

  local grd_dir="$HUMAN_HOME/.local/share/gnome-remote-desktop"
  sudo install -d -o "$HUMAN_USER_NAME" -g "$HUMAN_GROUP" -m 0700 "$grd_dir"
  if [ ! -f "$grd_dir/tls.key" ] || [ ! -f "$grd_dir/tls.crt" ]; then
    log "### rdp: creating GNOME Remote Desktop TLS certificate"
    generate_tls_cert "$grd_dir/tls.key" "$grd_dir/tls.crt"
  fi

  sudo systemctl disable --now gnome-remote-desktop.service >/dev/null 2>&1 || true
  sudo systemctl daemon-reload

  if [ -n "${VM_USER_PASSWORD:-}" ]; then
    log "### rdp: initializing GNOME keyring for Remote Desktop credentials"
    sudo install -d -o "$HUMAN_USER_NAME" -g "$HUMAN_GROUP" -m 0700 "$HUMAN_HOME/.local/share/keyrings"
    printf '%s' "$VM_USER_PASSWORD" |
      human_run gnome-keyring-daemon --daemonize --unlock --components=secrets >/dev/null 2>&1 || true
  fi

  human_run grdctl rdp set-tls-key "$grd_dir/tls.key"
  human_run grdctl rdp set-tls-cert "$grd_dir/tls.crt"
  human_run grdctl rdp set-credentials "$gate_user" "$gate_password"
  human_run grdctl rdp set-auth-methods credentials
  human_run grdctl rdp disable-view-only
  human_run grdctl rdp set-port "$rdp_port"
  human_run grdctl rdp enable

  if [ "$headless" = "headless" ]; then
    local width="${VIRTUAL_MONITOR_WIDTH:-1920}"
    local height="${VIRTUAL_MONITOR_HEIGHT:-1080}"
    if grdctl_supports "set-virtual-monitor"; then
      log "### rdp: configuring GNOME virtual monitor ${width}x${height}"
      human_run grdctl rdp set-virtual-monitor "${width}x${height}" || true
    elif command -v mutter >/dev/null 2>&1; then
      log "### rdp: enabling fallback headless Mutter virtual monitor ${width}x${height}"
      sudo install -d -o "$HUMAN_USER_NAME" -g "$HUMAN_GROUP" -m 0700 "$HUMAN_HOME/.config/systemd/user/default.target.wants"
      sudo tee "$HUMAN_HOME/.config/systemd/user/egame-headless-mutter.service" >/dev/null <<EOF
[Unit]
Description=Egame headless Mutter virtual monitor
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=$(command -v mutter) --wayland --headless --virtual-monitor ${width}x${height}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
EOF
      sudo chown "$HUMAN_USER_NAME:$HUMAN_GROUP" "$HUMAN_HOME/.config/systemd/user/egame-headless-mutter.service"
      sudo ln -sfn "$HUMAN_HOME/.config/systemd/user/egame-headless-mutter.service" \
        "$HUMAN_HOME/.config/systemd/user/default.target.wants/egame-headless-mutter.service"
      sudo chown -h "$HUMAN_USER_NAME:$HUMAN_GROUP" "$HUMAN_HOME/.config/systemd/user/default.target.wants/egame-headless-mutter.service"
      human_run systemctl --user daemon-reload || true
      human_run systemctl --user enable --now egame-headless-mutter.service || true
    fi
  fi

  human_run systemctl --user enable gnome-remote-desktop.service
  human_run systemctl --user restart gnome-remote-desktop.service || true
}

configure_krdp() {
  local headless="$1"
  log "### rdp: configuring KDE krdp (${headless})"

  apt_install \
    dbus-x11 \
    flatpak \
    kde-plasma-desktop \
    krdp \
    openssl \
    sddm

  configure_sddm_autologin
  start_human_user_manager

  if [ "$headless" = "headless" ]; then
    log "### rdp: disabling KDE lock and power management"
    human_run kwriteconfig6 --file kscreenlockerrc --group Daemon --key Autolock false || true
    human_run kwriteconfig6 --file kscreenlockerrc --group Daemon --key LockOnResume false || true
    human_run kwriteconfig6 --file kscreenlockerrc --group Daemon --key Timeout 0 || true
    for profile in Battery AC LowBattery; do
      human_run kwriteconfig6 --file powermanagementprofilesrc --group "$profile" --key DimDisplay false || true
      human_run kwriteconfig6 --file powermanagementprofilesrc --group "$profile" --key LockScreen false || true
      human_run kwriteconfig6 --file powermanagementprofilesrc --group "$profile" --key SleepComputer 0 || true
      human_run kwriteconfig6 --file powermanagementprofilesrc --group "$profile" --key SleepDisplay 0 || true
    done
  fi

  local krdp_dir="$HUMAN_HOME/.local/share/krdpserver"
  sudo install -d -o "$HUMAN_USER_NAME" -g "$HUMAN_GROUP" -m 0700 "$krdp_dir"
  if [ ! -f "$krdp_dir/krdp.key" ] || [ ! -f "$krdp_dir/krdp.crt" ]; then
    log "### rdp: creating krdp TLS certificate"
    generate_tls_cert "$krdp_dir/krdp.key" "$krdp_dir/krdp.crt"
  fi

  human_run kwriteconfig6 --file krdpserverrc --group General --key Certificate "$krdp_dir/krdp.crt"
  human_run kwriteconfig6 --file krdpserverrc --group General --key CertificateKey "$krdp_dir/krdp.key"
  human_run kwriteconfig6 --file krdpserverrc --group General --key Port "$rdp_port"
  human_run kwriteconfig6 --file krdpserverrc --group General --key SystemUserEnabled false

  for appid in org.kde.krdpserver org.kde.krdp-server org.kde.krdp-server.desktop; do
    for table in remote-desktop screencast; do
      human_run flatpak permission-set kde-authorized "$table" "$appid" yes >/dev/null 2>&1 || true
    done
  done

  local wants="$HUMAN_HOME/.config/systemd/user/plasma-workspace.target.wants"
  sudo install -d -o "$HUMAN_USER_NAME" -g "$HUMAN_GROUP" -m 0755 "$wants"
  sudo ln -sfn /usr/lib/systemd/user/app-org.kde.krdpserver.service "$wants/app-org.kde.krdpserver.service"
  sudo chown -h "$HUMAN_USER_NAME:$HUMAN_GROUP" "$wants/app-org.kde.krdpserver.service"

  local creds_dir="$HUMAN_HOME/.config/krdp"
  local creds_file="$creds_dir/credentials.env"
  sudo install -d -o "$HUMAN_USER_NAME" -g "$HUMAN_GROUP" -m 0700 "$creds_dir"
  sudo tee "$creds_file" >/dev/null <<EOF
KRDP_USER=$HUMAN_USER_NAME
KRDP_PASSWORD=${VM_USER_PASSWORD:-}
EOF
  sudo chown "$HUMAN_USER_NAME:$HUMAN_GROUP" "$creds_file"
  sudo chmod 0600 "$creds_file"

  local override_dir="$HUMAN_HOME/.config/systemd/user/app-org.kde.krdpserver.service.d"
  sudo install -d -o "$HUMAN_USER_NAME" -g "$HUMAN_GROUP" -m 0700 "$override_dir"
  sudo tee "$override_dir/override.conf" >/dev/null <<EOF
[Service]
EnvironmentFile=$creds_file
ExecStart=
ExecStart=/usr/bin/krdpserver -u \${KRDP_USER} -p \${KRDP_PASSWORD}
EOF
  sudo chown -R "$HUMAN_USER_NAME:$HUMAN_GROUP" "$override_dir"
  sudo chmod 0600 "$override_dir/override.conf"

  human_run systemctl --user daemon-reload || true
  human_run systemctl --user restart app-org.kde.krdpserver.service || true
}

configure_xrdp_xfce() {
  local headless="$1"
  log "### rdp: configuring xrdp/XFCE (${headless})"

  apt_install \
    dbus-x11 \
    openssl \
    xfce4 \
    xfce4-terminal \
    xorgxrdp \
    xrdp \
    xterm

  configure_xfce_xsession
  if [ "$headless" = "headless" ]; then
    disable_xfce_locks
    sudo systemctl disable --now lightdm.service gdm.service gdm3.service sddm.service >/dev/null 2>&1 || true
    sudo systemctl set-default multi-user.target
  else
    apt_install lightdm
    configure_lightdm_autologin
  fi

  sudo adduser xrdp ssl-cert >/dev/null 2>&1 || true
  sudo systemctl enable --now xrdp.service
  sudo systemctl restart xrdp.service
}

if has_selected_pkg gnome-desktop-headless; then
  configure_gnome_rdp headless
elif has_selected_pkg gnome-desktop; then
  configure_gnome_rdp local
elif has_selected_pkg kde-desktop-headless; then
  configure_krdp headless
elif has_selected_pkg kde-desktop; then
  configure_krdp local
elif has_selected_pkg xfce-desktop-headless; then
  configure_xrdp_xfce headless
else
  configure_xrdp_xfce local
fi

log "### rdp: done"
