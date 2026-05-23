#!/usr/bin/env bash
# Shared helpers for linux provisioning steps.
# Sourced by each step script via:  . "$PROVISION_ROOT/scripts/lib/common.sh"

set -euo pipefail

PROVISION_ROOT="${PROVISION_ROOT:-$HOME/provision}"
STATE_DIR="$PROVISION_ROOT/state"
LOGS_DIR="$PROVISION_ROOT/logs"
DOWNLOADS_DIR="$PROVISION_ROOT/downloads"
REBOOT_FLAG="$STATE_DIR/reboot.flag"
BUNDLE_PACKAGES_FILE="$STATE_DIR/bundle_packages"
SELECTED_PACKAGES_FILE="$STATE_DIR/selected_packages"
PROVISION_USER_NAME="${PROVISION_USER_NAME:-${USER:-$(id -un)}}"
HUMAN_USER_NAME="${HUMAN_USER_NAME:-${VM_USER_NAME:-$PROVISION_USER_NAME}}"
if id "$HUMAN_USER_NAME" >/dev/null 2>&1; then
  HUMAN_HOME="$(getent passwd "$HUMAN_USER_NAME" | awk -F: '{print $6}')"
  HUMAN_GROUP="$(id -gn "$HUMAN_USER_NAME")"
  HUMAN_UID="$(id -u "$HUMAN_USER_NAME")"
else
  HUMAN_HOME="$HOME"
  HUMAN_GROUP="$(id -gn)"
  HUMAN_UID="$(id -u)"
fi
HUMAN_HOME="${HUMAN_HOME:-$HOME}"

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

mkdir -p "$STATE_DIR" "$LOGS_DIR" "$DOWNLOADS_DIR"

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

has_pkg() {
  [ -f "$BUNDLE_PACKAGES_FILE" ] || return 1
  grep -Fqx "$1" "$BUNDLE_PACKAGES_FILE"
}

has_selected_pkg() {
  if [ -f "$SELECTED_PACKAGES_FILE" ]; then
    grep -Fqx "$1" "$SELECTED_PACKAGES_FILE"
    return
  fi
  has_pkg "$1"
}

skip_unless_pkg() {
  if ! has_pkg "$1"; then
    log "skip: package '$1' not in bundle"
    exit 0
  fi
}

apt_wait() {
  if command -v cloud-init >/dev/null 2>&1; then
    timeout 600 cloud-init status --wait >/dev/null 2>&1 || true
  fi

  local waited=0
  local max_wait=600
  while sudo fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock >/dev/null 2>&1; do
    if [ "$waited" -eq 0 ]; then
      log "waiting for apt/dpkg lock"
    fi
    if [ "$waited" -ge "$max_wait" ]; then
      log "apt/dpkg lock still held after ${max_wait}s"
      return 1
    fi
    sleep 5
    waited=$((waited + 5))
  done
}

apt_install() {
  apt_wait
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@"
}

apt_update_once() {
  local stamp="$STATE_DIR/apt_updated"
  [ -f "$stamp" ] && return 0
  apt_wait
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -y
  touch "$stamp"
}

download() {
  local url="$1"
  local out="$2"
  [ -f "$out" ] && { log "already downloaded: $out"; return 0; }
  mkdir -p "$(dirname "$out")"
  curl -fsSL --retry 8 --retry-delay 3 --retry-all-errors --connect-timeout 20 -o "$out" "$url"
}

request_reboot() {
  touch "$REBOOT_FLAG"
  log "reboot requested"
}

human_install_dir() {
  sudo install -d -o "$HUMAN_USER_NAME" -g "$HUMAN_GROUP" "$@"
}

repair_human_desktop_dirs() {
  human_install_dir \
    "$HUMAN_HOME/.config" \
    "$HUMAN_HOME/.cache" \
    "$HUMAN_HOME/.local" \
    "$HUMAN_HOME/.local/share" \
    "$HUMAN_HOME/Desktop" \
    "$HUMAN_HOME/Documents" \
    "$HUMAN_HOME/Downloads" \
    "$HUMAN_HOME/Music" \
    "$HUMAN_HOME/Pictures" \
    "$HUMAN_HOME/Public" \
    "$HUMAN_HOME/Templates" \
    "$HUMAN_HOME/Videos"
  sudo install -D -o "$HUMAN_USER_NAME" -g "$HUMAN_GROUP" -m 0644 /dev/stdin "$HUMAN_HOME/.config/user-dirs.dirs" <<'EOF'
XDG_DESKTOP_DIR="$HOME/Desktop"
XDG_DOWNLOAD_DIR="$HOME/Downloads"
XDG_TEMPLATES_DIR="$HOME/Templates"
XDG_PUBLICSHARE_DIR="$HOME/Public"
XDG_DOCUMENTS_DIR="$HOME/Documents"
XDG_MUSIC_DIR="$HOME/Music"
XDG_PICTURES_DIR="$HOME/Pictures"
XDG_VIDEOS_DIR="$HOME/Videos"
EOF
  sudo chown -R "$HUMAN_USER_NAME:$HUMAN_GROUP" \
    "$HUMAN_HOME/.config" \
    "$HUMAN_HOME/.cache" \
    "$HUMAN_HOME/.local" \
    "$HUMAN_HOME/Desktop" \
    "$HUMAN_HOME/Documents" \
    "$HUMAN_HOME/Downloads" \
    "$HUMAN_HOME/Music" \
    "$HUMAN_HOME/Pictures" \
    "$HUMAN_HOME/Public" \
    "$HUMAN_HOME/Templates" \
    "$HUMAN_HOME/Videos"
}

ensure_xfce_terminal() {
  local helper_dir="$HUMAN_HOME/.config/xfce4"
  local helper_file="$helper_dir/helpers.rc"
  apt_install xfce4-terminal xterm
  human_install_dir "$helper_dir"

  if sudo test -f "$helper_file"; then
    if sudo grep -q '^TerminalEmulator=' "$helper_file"; then
      sudo sed -i 's/^TerminalEmulator=.*/TerminalEmulator=xfce4-terminal/' "$helper_file"
    else
      printf '\nTerminalEmulator=xfce4-terminal\n' | sudo tee -a "$helper_file" >/dev/null
    fi
  else
    printf 'TerminalEmulator=xfce4-terminal\n' | human_write_file "$helper_file" 0644
  fi
  sudo chown "$HUMAN_USER_NAME:$HUMAN_GROUP" "$helper_file"
}

human_write_file() {
  local path="$1"
  local mode="${2:-0644}"
  local tmp
  tmp=$(mktemp)
  cat > "$tmp"
  sudo install -D -o "$HUMAN_USER_NAME" -g "$HUMAN_GROUP" -m "$mode" "$tmp" "$path"
  rm -f "$tmp"
}

human_run() {
  sudo -H -u "$HUMAN_USER_NAME" env \
    HOME="$HUMAN_HOME" \
    USER="$HUMAN_USER_NAME" \
    LOGNAME="$HUMAN_USER_NAME" \
    XDG_RUNTIME_DIR="/run/user/$HUMAN_UID" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$HUMAN_UID/bus" \
    "$@"
}

start_human_user_manager() {
  sudo loginctl enable-linger "$HUMAN_USER_NAME" >/dev/null 2>&1 || true
  sudo systemctl start "user@$HUMAN_UID.service" >/dev/null 2>&1 || true
}

generate_tls_cert() {
  local key_path="$1"
  local crt_path="$2"
  local owner="${3:-$HUMAN_USER_NAME}"
  local group="${4:-$HUMAN_GROUP}"

  sudo install -d -o "$owner" -g "$group" -m 0700 "$(dirname "$key_path")"
  sudo openssl req -x509 -nodes -newkey rsa:4096 \
    -keyout "$key_path" \
    -out "$crt_path" \
    -days 3650 \
    -subj "/CN=$(hostname)" >/dev/null 2>&1
  sudo chown "$owner:$group" "$key_path" "$crt_path"
  sudo chmod 0600 "$key_path"
  sudo chmod 0644 "$crt_path"
}

configure_gdm_autologin() {
  sudo systemctl set-default graphical.target
  sudo mkdir -p /etc/gdm3
  sudo tee /etc/gdm3/custom.conf >/dev/null <<EOF
[daemon]
AutomaticLoginEnable=True
AutomaticLogin=$HUMAN_USER_NAME
WaylandEnable=true

[security]

[xdmcp]

[chooser]

[debug]
EOF
  sudo install -d -m 0755 /var/lib/AccountsService/users
  sudo tee "/var/lib/AccountsService/users/$HUMAN_USER_NAME" >/dev/null <<EOF
[User]
Session=ubuntu
XSession=ubuntu
SystemAccount=false
EOF
  printf '/usr/sbin/gdm3\n' | sudo tee /etc/X11/default-display-manager >/dev/null
  sudo systemctl disable --now lightdm.service sddm.service xrdp.service >/dev/null 2>&1 || true
  sudo systemctl enable --now gdm.service >/dev/null 2>&1 ||
    sudo systemctl enable --now gdm3.service >/dev/null 2>&1 || true
}

disable_gnome_first_run_and_locks() {
  repair_human_desktop_dirs
  human_run gsettings set org.gnome.desktop.session idle-delay 0 >/dev/null 2>&1 || true
  human_run gsettings set org.gnome.desktop.screensaver lock-enabled false >/dev/null 2>&1 || true
  if human_run gsettings list-keys org.gnome.desktop.screensaver 2>/dev/null | grep -qx "ubuntu-lock-on-suspend"; then
    human_run gsettings set org.gnome.desktop.screensaver ubuntu-lock-on-suspend false >/dev/null 2>&1 || true
  fi
  sudo touch "$HUMAN_HOME/.config/gnome-initial-setup-done"
  sudo install -d -o "$HUMAN_USER_NAME" -g "$HUMAN_GROUP" -m 0700 "$HUMAN_HOME/.config/gnome-initial-setup"
  if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    [ -z "${VERSION_ID:-}" ] || sudo touch "$HUMAN_HOME/.config/gnome-initial-setup/upgrade-${VERSION_ID}-done"
  fi
  sudo chown -R "$HUMAN_USER_NAME:$HUMAN_GROUP" \
    "$HUMAN_HOME/.config/gnome-initial-setup" \
    "$HUMAN_HOME/.config/gnome-initial-setup-done"
}

configure_lightdm_autologin() {
  sudo systemctl set-default graphical.target
  sudo install -d -m 0755 /etc/lightdm/lightdm.conf.d
  sudo tee /etc/lightdm/lightdm.conf.d/autologin.conf >/dev/null <<EOF
[SeatDefaults]
autologin-user=$HUMAN_USER_NAME
autologin-user-timeout=0
EOF
  printf '/usr/sbin/lightdm\n' | sudo tee /etc/X11/default-display-manager >/dev/null
  sudo systemctl disable --now gdm.service gdm3.service sddm.service >/dev/null 2>&1 || true
  sudo systemctl enable lightdm.service >/dev/null 2>&1 || true
}

configure_sddm_autologin() {
  sudo systemctl set-default graphical.target
  sudo mkdir -p /etc/sddm.conf.d
  sudo tee /etc/sddm.conf.d/krdp-autologin.conf >/dev/null <<EOF
[Autologin]
User=$HUMAN_USER_NAME
Session=plasma
Relogin=true
EOF
  printf '/usr/bin/sddm\n' | sudo tee /etc/X11/default-display-manager >/dev/null
  sudo systemctl disable --now gdm.service gdm3.service lightdm.service xrdp.service >/dev/null 2>&1 || true
  sudo systemctl enable sddm.service >/dev/null 2>&1 || true
}

configure_xfce_xsession() {
  repair_human_desktop_dirs
  cat <<'EOF' | human_write_file "$HUMAN_HOME/.xsession" 0644
#!/usr/bin/env sh
unset DBUS_SESSION_BUS_ADDRESS
unset SESSION_MANAGER
export XDG_SESSION_TYPE=x11
export XDG_CURRENT_DESKTOP=XFCE
exec dbus-run-session -- startxfce4
EOF
  ensure_xfce_terminal
}

disable_xfce_locks() {
  sudo install -d -o "$HUMAN_USER_NAME" -g "$HUMAN_GROUP" -m 0700 "$HUMAN_HOME/.config/xfce4/xfconf/xfce-perchannel-xml"
  cat <<'EOF' | human_write_file "$HUMAN_HOME/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-screensaver.xml" 0644
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-screensaver" version="1.0">
  <property name="saver" type="empty">
    <property name="mode" type="int" value="0"/>
    <property name="enabled" type="bool" value="false"/>
  </property>
  <property name="lock" type="empty">
    <property name="enabled" type="bool" value="false"/>
  </property>
</channel>
EOF
  cat <<'EOF' | human_write_file "$HUMAN_HOME/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-power-manager.xml" 0644
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-power-manager" version="1.0">
  <property name="xfce4-power-manager" type="empty">
    <property name="blank-on-ac" type="int" value="0"/>
    <property name="blank-on-battery" type="int" value="0"/>
    <property name="dpms-on-ac-sleep" type="int" value="0"/>
    <property name="dpms-on-battery-sleep" type="int" value="0"/>
    <property name="dpms-on-ac-off" type="int" value="0"/>
    <property name="dpms-on-battery-off" type="int" value="0"/>
    <property name="lock-screen-suspend-hibernate" type="bool" value="false"/>
    <property name="logind-handle-lid-switch" type="bool" value="false"/>
  </property>
</channel>
EOF
}
