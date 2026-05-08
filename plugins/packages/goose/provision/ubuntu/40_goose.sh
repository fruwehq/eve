#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg goose

log "### 40_goose: installing Goose CLI"

if human_run sh -lc 'command -v goose >/dev/null 2>&1'; then
  log "goose already installed — skipping"
  exit 0
fi

apt_install bzip2

human_run sh -lc '
set -euo pipefail
cd "$HOME"
case "$(uname -m)" in
  aarch64|arm64) target="aarch64-unknown-linux-gnu" ;;
  x86_64|amd64) target="x86_64-unknown-linux-gnu" ;;
  *) echo "unsupported Goose architecture: $(uname -m)" >&2; exit 1 ;;
esac
tmpdir="$(mktemp -d)"
trap "rm -rf \"$tmpdir\"" EXIT
asset="goose-${target}.tar.bz2"
url="https://github.com/aaif-goose/goose/releases/download/stable/${asset}"
mkdir -p "$HOME/.local/bin"
curl -fL --retry 3 --retry-delay 2 -o "$tmpdir/$asset" "$url"
tar -xjf "$tmpdir/$asset" -C "$tmpdir"
binary="$(find "$tmpdir" -type f -name goose -perm -111 | head -n 1)"
if [ -z "$binary" ]; then
  echo "Goose archive did not contain an executable goose binary" >&2
  exit 1
fi
install -m 0755 "$binary" "$HOME/.local/bin/goose"
"$HOME/.local/bin/goose" --version
'

log "### 40_goose: done"
