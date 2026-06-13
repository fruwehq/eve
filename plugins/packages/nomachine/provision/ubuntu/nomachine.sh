#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg nomachine

log "### nomachine: installing NoMachine NX server"

repair_human_desktop_dirs

# NoMachine does not publish a stable "latest" download URL, so the version is
# pinned here and overridable via NOMACHINE_VERSION (e.g. 8.16.1_1). The build
# suffix after the underscore is part of the asset name and the URL's minor dir.
nomachine_version="${NOMACHINE_VERSION:-8.16.1_1}"
nomachine_minor="${nomachine_version%.*}"
nomachine_minor="${nomachine_minor%_*}"

if [ ! -x /usr/NX/bin/nxserver ]; then
  arch=$(dpkg --print-architecture)
  case "$arch" in
    amd64) deb_arch="amd64" ;;
    arm64) deb_arch="arm64" ;;
    *) log "### nomachine: unsupported arch for NoMachine: $arch"; exit 1 ;;
  esac

  asset="nomachine_${nomachine_version}_${deb_arch}.deb"
  url="https://download.nomachine.com/download/${nomachine_minor}/Linux/${asset}"
  deb="$DOWNLOADS_DIR/$asset"
  log "### nomachine: downloading $asset"
  download "$url" "$deb"
  apt_wait
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$deb"
else
  log "### nomachine: NoMachine already installed — skipping install"
fi

if [ ! -x /usr/NX/bin/nxserver ]; then
  log "### nomachine: /usr/NX/bin/nxserver missing after install"
  exit 1
fi

# NoMachine authenticates against the system account (PAM), so the human user
# must have a usable password. human-user.sh provisions it; surface the failure
# here rather than silently shipping an unreachable NX server.
if ! sudo passwd -S "$HUMAN_USER_NAME" 2>/dev/null | awk '{exit ($2=="P")?0:1}'; then
  log "### nomachine: warn: $HUMAN_USER_NAME has no usable password; NX login will fail until one is set"
fi

# NoMachine's .deb installs and starts nxserver via its own init; make sure the
# server is running so the instance is reachable immediately after provisioning.
log "### nomachine: starting NX server"
sudo /usr/NX/bin/nxserver --startup >/dev/null 2>&1 || true
sudo /usr/NX/bin/nxserver --status >/dev/null 2>&1 || \
  log "### nomachine: warn: nxserver status check did not report running"

log "### nomachine: done"
