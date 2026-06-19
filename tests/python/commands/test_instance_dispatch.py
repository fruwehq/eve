"""Behavior parity for the instance-* dispatchers (Phase 2 bash->Python port).

Drives scripts/instance-password, instance-provision, instance-run as
subprocesses and asserts the CLI contract for the seams that do not require a
live instance/SSH/cloud: usage/missing-arg handling and exit codes, the
instance-password os_family/provider gates (incl. the EPHEMERAL_WINDOWS_PASSWORD
override), the instance-provision --dry-run JSON contract, and instance-run
dispatch selection (env/validate/show-password + the unsupported-target branch).

No real VM, SSH, terraform, or cloud credentials are required: instance-run's
``env``/``validate`` targets resolve locally through instance-resolve, and the
``show-password`` dispatch reaches instance-password's not-a-Windows-profile
gate (exit 2) without touching terraform.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

ROOT = Path(__file__).resolve().parents[3]
_FIXTURE = ROOT / "tests" / "fixtures" / "instances.yaml"

# Catalog profiles for the instance-password gates: ubuntu (not-windows) and a
# windows profile on a non-vultr provider (aws -> "not implemented").
_PASSWORD_CATALOG = dedent(
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
def password_env(base_env: dict[str, str], tmp_path: Path) -> dict[str, str]:
    """Env with a temp catalog exposing ubuntu/windows profiles for the gates."""
    catalog = tmp_path / "password-catalog.local.yaml"
    catalog.write_text(_PASSWORD_CATALOG)
    return {**base_env, "EVE_CATALOG_LOCAL": str(catalog)}


@pytest.fixture()
def instance_env(base_env: dict[str, str]) -> dict[str, str]:
    """Env pointed at the fixture instance registry (mock-dev-a etc.)."""
    return {**base_env, "EVE_INSTANCE_REGISTRY": str(_FIXTURE)}


def _run(script: str, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=ROOT, text=True, capture_output=True, check=False, env=env,
    )


# ------------------------------- instance-password ------------------------ #
def test_instance_password_missing_arg(password_env: dict[str, str]) -> None:
    result = _run("instance-password", env=password_env)
    assert result.returncode == 2
    assert "Usage: scripts/instance-password <instance>" in result.stderr
    assert result.stdout == ""


def test_instance_password_override_short_circuits(base_env: dict[str, str]) -> None:
    # EPHEMERAL_WINDOWS_PASSWORD is honored before resolution; any name works.
    env = {**base_env, "EPHEMERAL_WINDOWS_PASSWORD": "hunter2"}
    result = _run("instance-password", "unused-profile", env=env)
    assert result.returncode == 0
    assert result.stdout == "hunter2\n"


def test_instance_password_rejects_non_windows_profile(
    password_env: dict[str, str],
) -> None:
    result = _run("instance-password", "ubuntu-test", env=password_env)
    assert result.returncode == 2
    assert (
        "[instance-password] ubuntu-test is not a Windows profile (os_family=ubuntu)"
        in result.stderr
    )


def test_instance_password_rejects_unimplemented_provider(
    password_env: dict[str, str],
) -> None:
    result = _run("instance-password", "windows-test", env=password_env)
    assert result.returncode == 2
    assert "[instance-password] not implemented for provider=mock-cloud" in result.stderr


# ------------------------------- instance-provision ----------------------- #
_PROVISION_USAGE = (
    "Usage: scripts/instance-provision --instance <name> "
    "[--registry <path>] [--force] [--dry-run]"
)


def test_instance_provision_missing_instance(instance_env: dict[str, str]) -> None:
    result = _run("instance-provision", "--force", env=instance_env)
    assert result.returncode == 2
    assert _PROVISION_USAGE in result.stderr


def test_instance_provision_unknown_arg(instance_env: dict[str, str]) -> None:
    result = _run("instance-provision", "--bogus", env=instance_env)
    assert result.returncode == 2
    assert _PROVISION_USAGE in result.stderr


def test_instance_provision_help_exits_zero(instance_env: dict[str, str]) -> None:
    result = _run("instance-provision", "--help", env=instance_env)
    assert result.returncode == 0
    assert _PROVISION_USAGE in result.stderr


def test_instance_provision_dry_run_emits_plan(instance_env: dict[str, str]) -> None:
    result = _run("instance-provision", "--instance", "mock-dev-a", "--dry-run", env=instance_env)
    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)
    assert doc["instance"] == "mock-dev-a"
    assert doc["command"] == "provision"
    assert doc["force"] is False
    assert doc["dry_run"] is True
    assert doc["overlay"].endswith("mock-dev-a/catalog.local.yaml")


def test_instance_provision_dry_run_force(instance_env: dict[str, str]) -> None:
    result = _run(
        "instance-provision", "--instance", "mock-dev-a", "--dry-run", "--force", env=instance_env,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["force"] is True


# --------------------------------- instance-run --------------------------- #
def test_instance_run_missing_target(instance_env: dict[str, str]) -> None:
    result = _run("instance-run", env=instance_env)
    assert result.returncode == 2
    assert "Usage: scripts/instance-run <make-target> [instance]" in result.stderr


def test_instance_run_missing_instance(instance_env: dict[str, str]) -> None:
    result = _run("instance-run", "env", env=instance_env)
    assert result.returncode == 2
    assert "instance-run: INSTANCE is required" in result.stderr
    assert "Usage: ./scripts/instance-run env <name>" in result.stderr


def test_instance_run_unsupported_target(instance_env: dict[str, str]) -> None:
    result = _run("instance-run", "bogus", "mock-dev-a", env=instance_env)
    assert result.returncode == 2
    assert "instance-run: unsupported target: bogus" in result.stderr


def test_instance_run_env_dispatch_resolves(instance_env: dict[str, str]) -> None:
    result = _run("instance-run", "env", "mock-dev-a", env=instance_env)
    assert result.returncode == 0, result.stderr
    assert "PROFILE_NAME=mock-dev-a" in result.stdout
    assert "PROVIDER=mock-cloud" in result.stdout


def test_instance_run_validate_dispatch(instance_env: dict[str, str]) -> None:
    result = _run("instance-run", "validate", "mock-dev-a", env=instance_env)
    assert result.returncode == 0, result.stderr


def test_instance_run_show_password_dispatches_to_password(
    instance_env: dict[str, str],
) -> None:
    # show-password -> instance-password; mock-dev-a is ubuntu so the not-a-Windows
    # gate fires (exit 2) without touching terraform/cloud.
    result = _run("instance-run", "show-password", "mock-dev-a", env=instance_env)
    assert result.returncode == 2
    assert "[instance-password] mock-dev-a is not a Windows profile (os_family=ubuntu)" in result.stderr
