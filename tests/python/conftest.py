"""Session setup: ensure the first-party plugins are synced.

After v4.0 Phase 3 the core ships no plugins — providers/packages are pulled from
the external repos into `repo_root/.eve/plugins`. Tests that load the catalog or
dispatch to a provider/package need them present, so sync once per session if the
synced tree is missing/empty (idempotent; a no-op once populated).
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from eve_sdk.workdir import Workdir


@pytest.fixture(scope="session", autouse=True)
def _ensure_plugins_synced() -> None:
    root = Workdir.repo_root()
    synced = root / ".eve" / "plugins"
    needs_sync = not synced.exists() or not any(synced.iterdir())
    if needs_sync:
        env = {key: value for key, value in os.environ.items() if key != "EVE_HOME"}
        subprocess.run(
            [sys.executable, str(root / "scripts" / "plugins-pull")],
            cwd=str(root), env=env, check=True, capture_output=True,
        )
