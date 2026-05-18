#!/usr/bin/env sh
# Load the same runtime configuration stack that Make uses:
# .env defaults, structured .egame/config.yaml, then .env.local overrides.

egame_load_dotenv() {
  file="$1"
  [ -f "$file" ] || return 0

  set -a
  # shellcheck disable=SC1090
  . "$file"
  set +a
}

if [ "${EGAME_RUNTIME_ENV_LOADED:-0}" != "1" ]; then
  export EGAME_RUNTIME_ENV_LOADED=1

  egame_load_dotenv ".env"

  if [ -x "./scripts/config-env" ]; then
    eval "$(./scripts/config-env --shell)"
  fi

  egame_load_dotenv ".env.local"
fi
