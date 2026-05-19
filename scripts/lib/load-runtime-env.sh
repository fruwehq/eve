#!/usr/bin/env sh
# Load the same runtime configuration stack that Make uses:
# .env defaults, structured .eve/config.yaml, then .env.local overrides.

eve_load_dotenv() {
  file="$1"
  [ -f "$file" ] || return 0

  set -a
  # shellcheck disable=SC1090
  . "$file"
  set +a
}

if [ "${EVE_RUNTIME_ENV_LOADED:-0}" != "1" ]; then
  export EVE_RUNTIME_ENV_LOADED=1

  eve_load_dotenv ".env"

  if [ -x "./scripts/config-env" ]; then
    eval "$(./scripts/config-env --shell)"
  fi

  eve_load_dotenv ".env.local"
fi
