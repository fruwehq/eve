#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg kde-desktop-headless

log "### kde-desktop-headless: installing KDE Plasma headless session"

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

log "### kde-desktop-headless: disabling KDE lock and power management"
human_run kwriteconfig6 --file kscreenlockerrc --group Daemon --key Autolock false || true
human_run kwriteconfig6 --file kscreenlockerrc --group Daemon --key LockOnResume false || true
human_run kwriteconfig6 --file kscreenlockerrc --group Daemon --key Timeout 0 || true
for profile in Battery AC LowBattery; do
  human_run kwriteconfig6 --file powermanagementprofilesrc --group "$profile" --key DimDisplay false || true
  human_run kwriteconfig6 --file powermanagementprofilesrc --group "$profile" --key LockScreen false || true
  human_run kwriteconfig6 --file powermanagementprofilesrc --group "$profile" --key SleepComputer 0 || true
  human_run kwriteconfig6 --file powermanagementprofilesrc --group "$profile" --key SleepDisplay 0 || true
done

log "### kde-desktop-headless: done"
