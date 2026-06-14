"""Shared helpers for the instance-* dispatcher scripts.

Wraps the subprocess calls the bash dispatchers made to
``scripts/lib/load-runtime-env.sh`` (the config-env shell loader) and
``scripts/instance-paths``, preserving the exact observed behavior under
``set -euo pipefail``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def load_runtime_env(root: Path) -> None:
    """Apply non-secret structured config via ``scripts/lib/load-runtime-env.sh``.

    Mirrors ``. ./scripts/lib/load-runtime-env.sh`` after ``cd "$ROOT"``: when
    ``EVE_RUNTIME_ENV_LOADED`` is unset/0 the loader marks itself loaded and
    ``eval``s ``./scripts/config-env --shell`` (when executable), applying the
    emitted exports to ``os.environ``. The loader runs under ``set -eu`` so a
    config-env failure is fatal with its exit status.
    """
    if os.environ.get("EVE_RUNTIME_ENV_LOADED") == "1":
        return
    loader = root / "scripts/lib/load-runtime-env.sh"
    result = subprocess.run(
        ["sh", "-eu", "-c", '. "$1" && env -0', "instance-run-loader", str(loader)],
        cwd=root, capture_output=True, check=False,
    )
    if result.returncode != 0:
        print("instance-run: runtime env loader failed:", file=sys.stderr)
        stderr = result.stderr.decode()
        if stderr.strip():
            print(stderr, end="", file=sys.stderr)
        raise SystemExit(result.returncode)
    for entry in result.stdout.split(b"\0"):
        if b"=" not in entry:
            continue
        key, value = entry.split(b"=", 1)
        os.environ[key.decode()] = value.decode()


def instance_paths_env(
    root: Path, instance: str, registry: str | None = None,
) -> dict[str, str]:
    """Resolve instance-scoped paths via ``scripts/instance-paths``.

    Mirrors ``INSTANCE_PATHS="$(./scripts/instance-paths ...)"``: propagate
    stderr and exit status (``set -e`` on the command substitution), then parse
    the emitted ``KEY=value`` lines into a dict. The value is everything after
    the first ``=``, matching the bash ``extract_path`` awk
    (``substr($0, index($0, "=") + 1)``).
    """
    cmd = [str(root / "scripts/instance-paths"), "--instance", instance, "--emit", "env"]
    if registry:
        cmd += ["--registry", registry]
    result = subprocess.run(cmd, cwd=root, text=True, capture_output=True, check=False)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    env: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value
    return env
