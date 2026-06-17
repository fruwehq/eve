"""Behavior parity for scripts ported bash->Python (Phase 2 migration)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _run(script: str, *args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=ROOT, text=True, capture_output=True, check=False, env=env,
    )


# --------------------------- env-require ----------------------------------- #
def test_env_require_no_args_is_usage_exit_2() -> None:
    result = _run("env-require")
    assert result.returncode == 2
    assert "usage:" in result.stderr.lower()


def test_env_require_all_set_passes() -> None:
    import os

    env = {**os.environ, "EVE_TEST_A": "1", "EVE_TEST_B": "x"}
    result = _run("env-require", "EVE_TEST_A", "EVE_TEST_B", env=env)
    assert result.returncode == 0, result.stderr


def test_env_require_lists_missing_and_exits_1() -> None:
    import os

    env = {k: v for k, v in os.environ.items() if k not in {"EVE_MISSING_X", "EVE_MISSING_Y"}}
    env["EVE_SET_Z"] = "ok"
    result = _run("env-require", "EVE_MISSING_X", "EVE_SET_Z", "EVE_MISSING_Y", env=env)
    assert result.returncode == 1
    assert "required environment variable(s) not set" in result.stderr
    assert "  - EVE_MISSING_X" in result.stderr
    assert "  - EVE_MISSING_Y" in result.stderr
    assert "EVE_SET_Z" not in result.stderr  # the set var is not reported


# --------------------------- ssh-retry ------------------------------------- #
def _fast_retry_env(attempts: int) -> dict:
    import os

    return {**os.environ, "EVE_SSH_RETRY_ATTEMPTS": str(attempts), "EVE_SSH_RETRY_DELAY": "0"}


def test_ssh_retry_missing_command_exit_2() -> None:
    result = _run("ssh-retry", "label-only")
    assert result.returncode == 2
    assert "missing command for label-only" in result.stderr


def test_ssh_retry_success_first_try() -> None:
    result = _run("ssh-retry", "ok", sys.executable, "-c", "raise SystemExit(0)", env=_fast_retry_env(6))
    assert result.returncode == 0
    assert result.stderr == ""  # no retry noise on success


def test_ssh_retry_exhausts_attempts_and_propagates_status() -> None:
    result = _run(
        "ssh-retry", "boom", sys.executable, "-c", "raise SystemExit(7)", env=_fast_retry_env(3)
    )
    assert result.returncode == 7
    assert "boom failed with exit 7; retrying in 0s (1/3)" in result.stderr
    assert "boom failed after 3 attempts (exit 7)" in result.stderr
