#!/usr/bin/env sh
# Load runtime configuration: structured config from config/defaults.yaml +
# .eve/config.yaml via config-env, then optional .env.local overrides.
# Secrets are loaded per-provider by profile-resolve at resolve time.

eve_load_dotenv() {
  file="$1"
  [ -f "$file" ] || return 0

  set -a
  # shellcheck disable=SC1090
  . "./$file"
  set +a
}

if [ "${EVE_RUNTIME_ENV_LOADED:-0}" != "1" ]; then
  export EVE_RUNTIME_ENV_LOADED=1

  if [ -x "./scripts/config-env" ]; then
    eval "$(./scripts/config-env --shell)"
  fi

  eve_load_dotenv ".env.local"
fi
