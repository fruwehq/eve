#!/usr/bin/env bash

eve_instance_workdir() {
  local instance_name="$1"
  local paths workdir
  if ! paths="$(./scripts/instance-paths --instance "$instance_name" --emit env)"; then
    return 1
  fi
  workdir="$(printf "%s\n" "$paths" | awk -F= '/^INSTANCE_WORKDIR=/{print substr($0, index($0, "=") + 1)}')"
  if [ -z "$workdir" ]; then
    echo "instance-workdir: INSTANCE_WORKDIR missing from scripts/instance-paths output" >&2
    return 1
  fi
  printf '%s\n' "$workdir"
}
