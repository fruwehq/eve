"""Generic shared spine for the remote-* launcher dispatch.

v4.4 §8 moved every per-client argv builder into its package (the launcher is an
action with ``exec``). What remains here is the generic spine the core dispatcher
(``scripts/package-action``) uses to build the shared ``EVE_REMOTE_*`` context —
identical for every client, with no package id.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    """Return ``git rev-parse --show-toplevel`` (errors propagate as under set -e)."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return Path(result.stdout.strip())


def resolve_env(root: Path, profile: str) -> dict[str, str]:
    """Resolve a profile to a KEY=value env dict via scripts/profile-resolve.

    Mirrors ``RESOLVED_ENV=$(./scripts/profile-resolve ...)``: stderr passes
    through, exit status propagates (set -e on the command substitution).
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


def instance_ip(root: Path, profile: str) -> str:
    """Return the instance IP via scripts/instance-ip.

    Mirrors ``IP=$(./scripts/instance-ip "$PROFILE")``: stderr passes through,
    exit status propagates under set -e.
    """
    result = subprocess.run(
        [str(root / "scripts/instance-ip"), profile],
        cwd=root, text=True, capture_output=True, check=False,
    )
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    return result.stdout.strip()


def resolve_private_key() -> str:
    """Resolve the SSH private key path from env, matching the bash convention.

    Mirrors::

        KEY_FILE="${SSH_PUBLIC_KEY_FILE:-}"
        if [ -n "$KEY_FILE" ] && [ "${KEY_FILE%.pub}" != "$KEY_FILE" ]; then
          PRIV_KEY="${KEY_FILE%.pub}"
        else
          PRIV_KEY="${SSH_PRIVATE_KEY_FILE:-}"
        fi
    """
    key_file = os.environ.get("SSH_PUBLIC_KEY_FILE", "")
    if key_file and key_file.endswith(".pub"):
        return key_file[:-4]
    return os.environ.get("SSH_PRIVATE_KEY_FILE", "")


def instance_workdir(root: Path, instance: str) -> str:
    """Resolve ``INSTANCE_WORKDIR`` via scripts/instance-paths.

    Propagate instance-paths stderr + exit status, then extract the
    INSTANCE_WORKDIR value (everything after the first ``=``).
    """
    result = subprocess.run(
        [str(root / "scripts/instance-paths"), "--instance", instance, "--emit", "env"],
        cwd=root, text=True, capture_output=True, check=False,
    )
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    for line in result.stdout.splitlines():
        if line.startswith("INSTANCE_WORKDIR="):
            return line.split("=", 1)[1]
    print(
        "instance-workdir: INSTANCE_WORKDIR missing from scripts/instance-paths output",
        file=sys.stderr,
    )
    raise SystemExit(1)
