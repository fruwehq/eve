#!/usr/bin/env sh
# Load runtime configuration: structured config from config/defaults.yaml +
# .eve/config.yaml via config-env. Secrets are loaded per-provider by
# profile-resolve at resolve time.

if [ "${EVE_RUNTIME_ENV_LOADED:-0}" != "1" ]; then
  export EVE_RUNTIME_ENV_LOADED=1

  if [ -x "./scripts/config-env" ]; then
    eval "$(./scripts/config-env --shell)"
  fi
fi
