"""Shared helpers for the tf-* terraform dispatcher scripts.

These wrap the subprocess calls the bash dispatchers made to
`scripts/profile-resolve` and `scripts/tf-env`, preserving the exact observed
behavior (stderr pass-through, `set -e` exit propagation, and the
command-substitution+eval env application of `eval "$(./scripts/tf-env ...)"`).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Characters bash's `printf '%q'` leaves unescaped; everything else is
# backslash-escaped. Used for the EVE_TF_PRINT=1 dry-run lines so the output
# matches the previous bash implementation byte-for-byte.
_BASH_QUOTE_SAFE = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "_@%+=:,./-!"
)


def quote_arg(value: str) -> str:
    """Quote one argument like bash `printf '%q'`."""
    if value == "":
        return "''"
    if all(c in _BASH_QUOTE_SAFE for c in value):
        return value
    return "".join(c if c in _BASH_QUOTE_SAFE else "\\" + c for c in value)


def repo_root() -> Path:
    """Return `git rev-parse --show-toplevel` (errors propagate, as under set -e)."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return Path(result.stdout.strip())


def resolve_env(root: Path, profile: str) -> dict[str, str]:
    """Resolve a profile to a KEY=value env dict via scripts/profile-resolve.

    Under `RESOLVED_ENV=$(./scripts/profile-resolve ...)` the bash scripts relied
    on set -e to exit with profile-resolve's status while letting its stderr pass
    through; this mirrors that.
    """
    result = subprocess.run(
        [str(root / "scripts/profile-resolve"), "--profile", profile, "--emit", "env"],
        cwd=root, text=True, capture_output=True, check=False,
    )
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


def apply_tf_env(root: Path, profile: str) -> None:
    """Run scripts/tf-env and apply its `export KEY=value;` lines to os.environ.

    Mirrors bash `eval "$(./scripts/tf-env "$PROFILE")"`: tf-env's stdout is
    consumed (parsed into env exports), its stderr passes through, and its exit
    status is not propagated — a partial failure leaves whatever exports were
    emitted applied, exactly as the command-substitution+eval form did.
    """
    result = subprocess.run(
        [str(root / "scripts/tf-env"), profile], cwd=root, text=True, capture_output=True,
        check=False,
    )
    sys.stderr.write(result.stderr)
    for line in result.stdout.splitlines():
        stripped = line.rstrip(";").strip()
        if stripped.startswith("export "):
            stripped = stripped[len("export "):]
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
            value = value[1:-1].replace("'\\''", "'")
        os.environ[key] = value


def prepare_provider_stacks(root: Path, provider_id: str) -> None:
    """Stage a provider's terramate stacks where terramate can discover them.

    After v4.0 externalized providers, the stacks live under
    ``.eve/plugins/<source>/<provider>/stacks/`` (a symlinked path terramate
    can't scan). The stack files reference root-relative paths like
    ``/plugins/providers/<provider>/stacks/...``, and manifests reference
    siblings like ``../_terraform-common/``, so we physically copy the entire
    source tree to ``plugins/providers/`` — terramate finds the stacks AND
    the sibling paths resolve. Safe to call repeatedly (idempotent).
    """
    import shutil

    from eve_sdk.plugin_manifest import PluginManifest

    # Find the materialized provider plugin path, then go up to the source root.
    plugin_path = None
    for plugin in PluginManifest.load_all("provider"):
        if plugin.get("id") == provider_id:
            plugin_path = Path(str(plugin["_path"])).parent
            break
    if plugin_path is None or not plugin_path.is_dir():
        return

    source_root = plugin_path.parent  # e.g. .eve/plugins/eve-providers/
    dest_root = root / "plugins" / "providers"

    # Copy the provider dir + all sibling dirs starting with _ (shared: _common, _terraform-common, etc.).
    # This ensures ../_terraform-common/ etc. resolve from the staged provider.
    needed = [provider_id] + [d.name for d in source_root.iterdir() if d.is_dir() and d.name.startswith("_")]
    for name in needed:
        src = source_root / name
        dst = dest_root / name
        if not src.is_dir():
            continue
        if dst.exists() or dst.is_symlink():
            if dst.is_symlink() or dst.is_file():
                dst.unlink()
            else:
                shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("eve-plugin.yaml"))
