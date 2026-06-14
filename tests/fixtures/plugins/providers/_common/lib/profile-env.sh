#!/usr/bin/env bash
# Shared profile-env loader for per-provider plugin commands.
# Sources resolved env exposed by scripts/profile-resolve (which consumes the
# SDK-validated EVE_RESOLVED_JSON when set) and exports the fields every
# per-provider command needs.
#
# Caller must have cd'd into the repo root before sourcing.
#
# Usage:
#   . plugins/providers/_common/lib/profile-env.sh "$PROFILE"
#
# Exports: RESOLVED_ENV, ENGINE, PROVIDER, OS_FAMILY, TAGS, SSH_USER

eve_load_profile_env() {
  local profile="$1"
  RESOLVED_ENV=$(./scripts/profile-resolve --profile "$profile" --emit env)
  ENGINE=$(printf "%s\n" "$RESOLVED_ENV" | awk -F= '/^ENGINE=/{print $2}')
  PROVIDER=$(printf "%s\n" "$RESOLVED_ENV" | awk -F= '/^PROVIDER=/{print $2}')
  OS_FAMILY=$(printf "%s\n" "$RESOLVED_ENV" | awk -F= '/^OS_FAMILY=/{print $2}')
  TAGS=$(printf "%s\n" "$RESOLVED_ENV" | awk -F= '/^STACK_TAGS=/{print $2}')
  SSH_USER=$(printf "%s\n" "$RESOLVED_ENV" | awk -F= '/^SSH_USER=/{print $2}')
  export RESOLVED_ENV ENGINE PROVIDER OS_FAMILY TAGS SSH_USER
}

eve_resolved_value() {
  printf "%s\n" "$RESOLVED_ENV" | awk -F= -v key="$1" '$1 == key { print substr($0, index($0, "=") + 1) }'
}

eve_normalize_path() {
  local value="$1"
  # shellcheck disable=SC2088,SC2016
  case "$value" in
    '$(HOME)'|'$(HOME)/'*) printf '%s' "$HOME${value#\$\(HOME\)}" ;;
    '$HOME'|'$HOME/'*) printf '%s' "$HOME${value#\$HOME}" ;;
    '~'|'~/'*) printf '%s' "$HOME${value#\~}" ;;
    *) printf '%s' "$value" ;;
  esac
}
