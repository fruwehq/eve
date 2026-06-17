"""Behavior parity for the misc leaf utilities (Phase 2 bash->Python port).

Drives scripts/logs, scripts/upload, scripts/update-tools, and
scripts/providers-status as subprocesses and asserts the CLI contract for the
seams that do not require a live instance/SSH/cloud: usage/missing-arg handling
and exit codes, the upload name-validation and missing-upload-dir gates, the
update-tools Windows-not-implemented guard, and the providers-status provider/
field validation (exercised via the network-free mock-cloud check).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

ROOT = Path(__file__).resolve().parents[3]

# Catalog exposing an ubuntu and a windows profile so profile-resolve can emit
# OS_FAMILY locally (no cloud). Mirrors the test_instance_dispatch fixture shape.
_MISC_CATALOG = dedent(
    """\
    profiles:
      - name: ubuntu-test
        machine: mock-small
        os: mockos-1.0-arm64
        init: ssh-mockos-cloud-init
        bundles: []
        location: mock-tokyo
      - name: windows-test
        machine: mock-gpu
        os: mockwin-1.0
        init: ssh-mockwin-powershell
        bundles: []
        location: mock-tokyo
    """
)


@pytest.fixture()
def base_env(tmp_path: Path) -> dict[str, str]:
    """Shared env: temp SSH key + temp workdir/state, INSTANCE unset."""
    key = tmp_path / "id_test.pub"
    key.write_text("ssh-rsa AAAAB3NzaC1yc2EAAAA_test_only test@test\n")
    env = {
        **os.environ,
        "SSH_PUBLIC_KEY_FILE": str(key),
        "VM_USER_NAME": "eve-test",
        "EVE_INSTANCE_WORKDIR": str(tmp_path / "work"),
        "EVE_STATE_DIR": str(tmp_path / "state"),
    }
    env.pop("INSTANCE", None)
    env.pop("EPHEMERAL_WINDOWS_PASSWORD", None)
    return env


@pytest.fixture()
def catalog_env(base_env: dict[str, str], tmp_path: Path) -> dict[str, str]:
    """Env with a temp catalog exposing ubuntu/windows profiles for resolution gates."""
    catalog = tmp_path / "misc-catalog.local.yaml"
    catalog.write_text(_MISC_CATALOG)
    return {**base_env, "EVE_CATALOG_LOCAL": str(catalog)}


def _run(script: str, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=ROOT, text=True, capture_output=True, check=False, env=env,
    )


# ----------------------------------- logs ---------------------------------- #
def test_logs_missing_arg(catalog_env: dict[str, str]) -> None:
    result = _run("logs", env=catalog_env)
    assert result.returncode == 2
    assert "Usage: scripts/logs <instance>" in result.stderr
    assert result.stdout == ""


# ---------------------------------- upload --------------------------------- #
def test_upload_missing_instance(catalog_env: dict[str, str]) -> None:
    result = _run("upload", env=catalog_env)
    assert result.returncode == 2
    assert "Usage: scripts/upload <instance> [upload-name ...]" in result.stderr


def test_upload_no_upload_dir_skips(base_env: dict[str, str], tmp_path: Path) -> None:
    # Exits before profile-resolve, so no catalog/instance is needed.
    env = {**base_env, "EVE_UPLOAD_DIR": str(tmp_path / "does-not-exist")}
    result = _run("upload", "whatever-profile", env=env)
    assert result.returncode == 0
    assert result.stdout == "No upload directory found. Skipping upload.\n"


def test_upload_rejects_invalid_name(catalog_env: dict[str, str], tmp_path: Path) -> None:
    env = {**catalog_env, "EVE_UPLOAD_DIR": str(tmp_path / "upload")}
    Path(tmp_path / "upload").mkdir()
    result = _run("upload", "ubuntu-test", "bad/name", env=env)
    assert result.returncode == 2
    assert "upload: invalid upload name: bad/name" in result.stderr


def test_upload_rejects_missing_folder(catalog_env: dict[str, str], tmp_path: Path) -> None:
    env = {**catalog_env, "EVE_UPLOAD_DIR": str(tmp_path / "upload")}
    Path(tmp_path / "upload").mkdir()
    result = _run("upload", "ubuntu-test", "missing", env=env)
    assert result.returncode == 2
    assert "upload: selected upload is not a direct folder under upload: missing" in result.stderr


# ------------------------------- update-tools ------------------------------ #
def test_update_tools_missing_arg(catalog_env: dict[str, str]) -> None:
    result = _run("update-tools", env=catalog_env)
    assert result.returncode == 2
    assert "Usage: scripts/update-tools <instance>" in result.stderr


def test_update_tools_windows_not_implemented(catalog_env: dict[str, str]) -> None:
    result = _run("update-tools", "windows-test", env=catalog_env)
    assert result.returncode == 1
    assert result.stdout == "Windows update not yet implemented\n"


# ----------------------------- providers-status ---------------------------- #
def test_providers_status_unknown_provider(catalog_env: dict[str, str]) -> None:
    result = _run("providers-status", "bogus", env=catalog_env)
    assert result.returncode == 1
    assert "Unknown provider: bogus" in result.stderr


def test_providers_status_unknown_field(catalog_env: dict[str, str]) -> None:
    # mock-cloud's check only probes for qemu binaries (network-free), so the
    # command reaches the field-validation gate deterministically.
    result = _run("providers-status", "mock-cloud", "bogusfield", env=catalog_env)
    assert result.returncode == 1
    assert "Unknown field: bogusfield (valid: configured, reachable, notes)" in result.stderr


def test_providers_status_table_header_for_local_qemu(
    catalog_env: dict[str, str],
) -> None:
    result = _run("providers-status", "mock-cloud", env=catalog_env)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "Provider           Configured  Reachable  Notes"
    assert lines[1] == "-----------------  ----------  ---------  -------------------------------------------"
    assert lines[2].startswith("mock-cloud        ")
