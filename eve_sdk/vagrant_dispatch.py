"""Shared helpers for the vagrant-* dispatcher scripts.

Wraps the subprocess call the bash dispatchers made to ``scripts/instance-paths``
(via ``scripts/lib/instance-workdir.sh``), preserving the exact observed
behavior under ``set -euo pipefail``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def instance_workdir(root: Path, profile: str) -> str:
    """Resolve the instance workdir via ``scripts/instance-paths``.

    Mirrors ``scripts/lib/instance-workdir.sh``'s ``eve_instance_workdir``: run
    ``scripts/instance-paths --instance <name> --emit env``, propagate its stderr
    and exit status (``set -e`` on the command substitution), then extract the
    ``INSTANCE_WORKDIR=`` value (everything after the first ``=``). If that key
    is missing, print the same diagnostic to stderr and exit 1.
    """
    result = subprocess.run(
        [str(root / "scripts/instance-paths"), "--instance", profile, "--emit", "env"],
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
