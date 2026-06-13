#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg splashtop

log "### splashtop: installing Splashtop Streamer"

repair_human_desktop_dirs

# The free Splashtop Streamer requires logging the host into a Splashtop account
# (free for same-LAN/VPN use). Fail fast with guidance when credentials are
# missing rather than shipping a streamer nobody can reach.
if [ -z "${SPLASHTOP_EMAIL:-}" ] || [ -z "${SPLASHTOP_PASSWORD:-}" ]; then
  log "### splashtop: SPLASHTOP_EMAIL and SPLASHTOP_PASSWORD are required"
  log "### splashtop: create a free Splashtop account and connect over the same LAN/VPN"
  exit 2
fi

# Splashtop gates streamer downloads behind an account, so this repo does not
# hard-code a hidden URL — provide SPLASHTOP_STREAMER_URL or _PATH (mirrors the
# ThinLinc server-bundle handling).
if [ -z "${SPLASHTOP_STREAMER_URL:-}" ] && [ -z "${SPLASHTOP_STREAMER_PATH:-}" ]; then
  log "### splashtop: SPLASHTOP_STREAMER_PATH or SPLASHTOP_STREAMER_URL is required"
  log "### splashtop: download the Linux Streamer .deb from your Splashtop account and point one of these at it"
  exit 2
fi

if ! command -v SRStreamer >/dev/null 2>&1 && [ ! -x /opt/splashtop-streamer/SRStreamer.sh ]; then
  arch=$(dpkg --print-architecture)
  if [ "$arch" != "amd64" ]; then
    log "### splashtop: unsupported arch for Splashtop Streamer: $arch (amd64 only)"
    exit 1
  fi

  deb="$DOWNLOADS_DIR/splashtop-streamer.deb"
  if [ -n "${SPLASHTOP_STREAMER_PATH:-}" ]; then
    if [ ! -e "$SPLASHTOP_STREAMER_PATH" ]; then
      log "### splashtop: SPLASHTOP_STREAMER_PATH not found: $SPLASHTOP_STREAMER_PATH"
      exit 2
    fi
    log "### splashtop: using uploaded streamer package $SPLASHTOP_STREAMER_PATH"
    cp "$SPLASHTOP_STREAMER_PATH" "$deb"
  else
    log "### splashtop: downloading streamer package"
    download "$SPLASHTOP_STREAMER_URL" "$deb"
  fi
  apt_wait
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$deb"
else
  log "### splashtop: Splashtop Streamer already installed — skipping install"
fi

streamer=""
for candidate in /opt/splashtop-streamer/SRStreamer.sh "$(command -v SRStreamer 2>/dev/null || true)"; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then
    streamer="$candidate"
    break
  fi
done
if [ -z "$streamer" ]; then
  log "### splashtop: streamer launcher not found after install"
  exit 1
fi

# Log the streamer into the Splashtop account so the host registers and becomes
# reachable from the paired client.
log "### splashtop: logging streamer into Splashtop account $SPLASHTOP_EMAIL"
if ! sudo "$streamer" account -login "$SPLASHTOP_EMAIL" "$SPLASHTOP_PASSWORD" >/dev/null 2>&1; then
  log "### splashtop: warn: streamer login command failed; verify the credentials and LAN/VPN reachability"
fi

sudo "$streamer" start >/dev/null 2>&1 || true

log "### splashtop: done"
