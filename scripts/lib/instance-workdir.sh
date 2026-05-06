#!/usr/bin/env bash

egame_instance_workdir() {
  local instance_name="$1"
  local paths workdir
  if paths="$(./scripts/instance-paths --instance "$instance_name" --emit env 2>/dev/null)"; then
    workdir="$(printf "%s\n" "$paths" | awk -F= '/^INSTANCE_WORKDIR=/{print substr($0, index($0, "=") + 1)}')"
    if [ -n "$workdir" ]; then
      printf '%s\n' "$workdir"
      return
    fi
  fi
  printf '.generated/%s\n' "$instance_name"
}
