#!/usr/bin/env bash
# Load Eve runtime environment, then run the requested command.

set -euo pipefail

cd /opt/eve

# shellcheck source=../scripts/lib/load-runtime-env.sh
. ./scripts/lib/load-runtime-env.sh

if [ "$#" -eq 0 ]; then
  set -- make eve
fi

exec "$@"
