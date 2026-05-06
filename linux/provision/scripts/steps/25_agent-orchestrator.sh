#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg agent-orchestrator

log "### 25_agent-orchestrator: installing agent-hub config"

AGENT_HUB_REPO="${AGENT_HUB_REPO:-https://github.com/fruwe/agent-hub.git}"
AGENT_HUB_BRANCH="${AGENT_HUB_BRANCH:-main}"
AGENT_HUB_REF="${AGENT_HUB_REF:-}"
INSTALL_PREFIX="${AGENT_HUB_INSTALL_PREFIX:-/opt/agent-hub}"

if [[ -d "$INSTALL_PREFIX/.git" ]]; then
  log "agent-hub already installed at $INSTALL_PREFIX — updating"
  git -C "$INSTALL_PREFIX" pull --ff-only || {
    log "WARNING: could not update agent-hub — using existing checkout"
  }
else
  log "cloning agent-hub from $AGENT_HUB_REPO (branch: $AGENT_HUB_BRANCH)"
  if [[ -n "$AGENT_HUB_REF" ]]; then
    git clone --branch "$AGENT_HUB_BRANCH" --single-branch "$AGENT_HUB_REPO" "$INSTALL_PREFIX"
    git -C "$INSTALL_PREFIX" checkout "$AGENT_HUB_REF"
  else
    git clone --branch "$AGENT_HUB_BRANCH" --single-branch "$AGENT_HUB_REPO" "$INSTALL_PREFIX"
  fi
fi

if [[ -f "$INSTALL_PREFIX/install.sh" ]]; then
  log "running agent-hub installer"
  export INSTALL_PREFIX
  bash "$INSTALL_PREFIX/install.sh"
else
  log "WARNING: install.sh not found in $INSTALL_PREFIX — skipping installer"
fi

log "### 25_agent-orchestrator: done"
