#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg docker

log "### 10_docker: installing rootless Docker CE"

uid="$(id -u)"
rootless_sock="/run/user/$uid/docker.sock"
if command -v docker >/dev/null 2>&1 && [ -S "$rootless_sock" ]; then
  log "rootless docker already installed — skipping"
  exit 0
fi

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --batch --yes --dearmor -o /etc/apt/keyrings/docker.gpg

# shellcheck disable=SC1091
codename=$(. /etc/os-release && echo "$VERSION_CODENAME")
arch=$(dpkg --print-architecture)
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu %s stable\n' \
  "$arch" "$codename" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo DEBIAN_FRONTEND=noninteractive apt-get update -y
apt_install \
  dbus-user-session \
  docker-ce \
  docker-ce-cli \
  docker-ce-rootless-extras \
  docker-buildx-plugin \
  docker-compose-plugin \
  slirp4netns \
  uidmap

sudo systemctl disable --now docker.service docker.socket >/dev/null 2>&1 || true
sudo loginctl enable-linger "$USER"
sudo systemctl start "user@$uid.service" || true

export XDG_RUNTIME_DIR="/run/user/$uid"
if [ ! -d "$XDG_RUNTIME_DIR" ]; then
  sudo install -d -m 700 -o "$USER" -g "$(id -gn)" "$XDG_RUNTIME_DIR"
fi
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"

if [ ! -f "$HOME/.config/systemd/user/docker.service" ]; then
  log "setting up rootless docker daemon for $USER"
  dockerd-rootless-setuptool.sh install --force
fi

systemctl --user daemon-reload
systemctl --user enable --now docker

# shellcheck disable=SC2016 # Written literally so each login shell resolves its own uid.
profile_line='export DOCKER_HOST="unix:///run/user/$(id -u)/docker.sock"'
if ! grep -Fqx "$profile_line" "$HOME/.profile" 2>/dev/null; then
  printf '\n# Rootless Docker daemon for ephemeral-cloud-gaming.\n%s\n' "$profile_line" >>"$HOME/.profile"
fi

export DOCKER_HOST="unix://$rootless_sock"
docker version >/dev/null

log "### 10_docker: done"
