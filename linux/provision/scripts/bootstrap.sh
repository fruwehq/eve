#!/usr/bin/env bash
# bootstrap.sh — entry point for linux provisioning.
#
# Responsibilities:
#   - Initializes provisioning directory layout under $HOME/provision.
#   - Writes the initial state.json (currentStep = 0) if missing.
#   - Installs a systemd unit so provisioning resumes after reboot.
#   - Kicks off runner.sh for the first pass.
#
# Intended to be uploaded by `make profile.provision` and run once per host.

set -euo pipefail

PROVISION_ROOT="${PROVISION_ROOT:-$HOME/provision}"
SCRIPTS_DIR="$PROVISION_ROOT/scripts"
STATE_DIR="$PROVISION_ROOT/state"
LOGS_DIR="$PROVISION_ROOT/logs"
STATE_FILE="$STATE_DIR/state.json"

mkdir -p "$STATE_DIR" "$LOGS_DIR"

if [ ! -f "$STATE_FILE" ]; then
  printf '{"currentStep":0}\n' > "$STATE_FILE"
fi

UNIT_PATH="/etc/systemd/system/ephemeral-provision.service"
sudo tee "$UNIT_PATH" >/dev/null <<EOF
[Unit]
Description=Ephemeral VM provisioning runner
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$USER
WorkingDirectory=$PROVISION_ROOT
Environment=PROVISION_ROOT=$PROVISION_ROOT
ExecStart=/usr/bin/env bash $SCRIPTS_DIR/runner.sh
StandardOutput=append:$LOGS_DIR/provision.log
StandardError=append:$LOGS_DIR/provision.log

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable ephemeral-provision.service >/dev/null

sudo systemctl restart --no-block ephemeral-provision.service
echo "Provisioning runner started via systemd."
